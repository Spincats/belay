#!/usr/bin/env python

import sys
import os
import yaml
import logging
import argparse
from slackclient import SlackClient

program_version="1.0"

logger = logging.getLogger(__name__)

def load_config(conf_path=None, team=None):
  # Try the usual places to store an API token
  # First token wins
  api_token = None
  bot_token = None
  config_data = {}
  homedir = os.path.expanduser("~")
  scriptdir = os.path.dirname(os.path.realpath(__file__))

  # 1. Specified config file
  if conf_path:
    logger.debug("Skipping standard config locations because config path passed in on the command line.") 
  # 2. ~/.config/slack/config.yml
  elif os.path.isfile(os.path.join(homedir,".config","belay","config.yml")):
    conf_path = os.path.join(homedir,".config","belay","config.yml")
    logger.info("Found config file in Home Directory: %s", conf_path)
  # 3. ./config.yml
  elif os.path.isfile(os.path.join(scriptdir,"config.yml")):
    conf_path = os.path.join(scriptdir,"config.yml")
    logger.info("Found config file in current script directory: %s", conf_path)
  # OK, now actually pull values from the configs
  if conf_path:
    logger.info("Attempting to load config from file.")
    with open(conf_path, "r") as config:
      config_data = yaml.load(config, Loader=yaml.loader.BaseLoader)
      logger.debug("Loaded config: %s", config_data)
    if "teams" in config_data:
      logger.debug("This is a multi-team config file. Script is looking for team: %s", team)
      if not team:
        raise ValueError("No team specified with multi-team config. Please indicate which team you'd like to use.")
      elif team not in config_data["teams"]:
        raise ValueError("Specified team '"+team+"' not present in config file. Valid choices are: "+", ".join(config_data["teams"].keys()))
      else:
        logger.debug("Team '%s' found. Selecting only data for that team.", team)
        config_data = config_data["teams"][team]
  # Allow people to set keys in the env if they don't want them in files
  # Clear bot if we find API, to try to avoid mixing teams
  if "SLACK_API_TOKEN" in os.environ:
    config_data.pop("bot_token", 0)
    config_data["api_token"] = os.environ["SLACK_API_TOKEN"]
    logger.info("Found API token in environment, adding to config from file.")
    logger.debug("API Token: %s", api_token)
    logger.info("Checking environment for SLACK_BOT_TOKEN variable...")
    if "SLACK_BOT_TOKEN" in os.environ:
      config_data["bot_token"] = os.environ["SLACK_BOT_TOKEN"]
      logger.info("Found bot token in environment, adding to config from file.")
      logger.debug("Bot Token: %s", bot_token)
   
  if "api_token" not in config_data:
    raise RuntimeError("No API token not found.")
  if "bot_token" not in config_data:
    logger.warn("No bot token provided. Assuming API token is legacy token. Use of legacy tokens is a potential security issue and we strongly recommend switching to the new token format.")
  return config_data

def belay(config):
  slack_api = SlackClient(config["api_token"])
  api_test = slack_api.api_call("auth.test")
  logger.debug("API Token auth.test results: %s", api_test)
  if not api_test["ok"]:
    raise ValueError("API Token is invalid.")
  api_user = slack_api.api_call("users.info", user=api_test["user_id"])
  logger.debug("User info for API token user: %s", api_user)
  if api_user["user"]["is_bot"]:
    raise ValueError("API Token is a bot token. This will not work.")
  if "bot_token" in config:
    slack_bot = SlackClient(config["bot_token"])
    bot_test = slack_bot.api_call("auth.test")
    logger.debug("Bot Token auth.test results: %s", bot_test)
    if not bot_test["ok"]:
      raise ValueError("Bot Token is invalid.")
    bot_user = slack_bot.api_call("users.info", user=bot_test["user_id"])
    logger.debug("User info for Bot token user: %s", bot_user)
    if not bot_user["user"]["is_bot"]:
      raise ValueError("Bot Token does not correspond to a bot user.")
  else:
    slack_bot = slack_api
  integration_issues = check_integrations(slack_api, config)
  if integration_issues:
    logger.info("Found the following integration issues: %s", integration_issues)
    notify_problems(integration_issues, config, slack_bot, "Problem Integrations:", "integration_name", "date")
  else:
    logger.info("No integration issues found.")
  user_issues = check_users(slack_api, config)  
  if user_issues:
    logger.info("Found the following user issues: %s", user_issues)
    notify_problems(user_issues, config, slack_bot, "Problem Users:", "name", "name")
  else:
    logger.info("No user issues found.")

def check_integrations(api_client, config):
  if "skip_integrations" in config and config["skip_integrations"]:
    return {}
  result = api_client.api_call("team.integrationLogs")
  logger.debug("Integration log results: %s", result)
  if not result["ok"]:
    raise RuntimeError("API Call encountered an error while getting initial integrations: "+unicode(result))
  iLogs = result["logs"]
  if result["paging"]["pages"] > 1:
    logger.info("Multiple pages of integration logs exist. Pulling remaining %s pages...", result["paging"]["pages"] - 1)
    while result["paging"]["page"] < result["paging"]["pages"]:
      nextPage = result["paging"]["page"] + 1
      logger.info("Pulling page %s.", nextPage)
      result = api_client.api_call("team.integrationLogs", page=nextPage)
      logger.debug("Page %s: %s", nextPage, result)
      if not result["ok"]:
        raise RuntimeError("API Call encountered an error while getting additional integrations: "+unicode(result))
      iLogs.extend(result["logs"])
  integrations = {}
  if "integration_whitelist" in config:
    integration_whitelist = config["integration_whitelist"]
  else:
    integration_whitelist = {}
  for log in iLogs:
    if log["change_type"] in ["added", "enabled", "updated", "expanded", "reissued"]:
      status = "active"
    elif log["change_type"] == "removed":
      status = "removed"
    elif log["change_type"] == "disabled":
      status = "disabled"
    else:
      status = "unknown"
      logger.warn("Unknown change type (%s) in integration log: %s", log["change_type"], log)
    if "scope" in log and log["scope"]:
      scopes = log["scope"].split(",")
    else:
      scopes = []
    if "app_id" in log:
      int_id = log["app_id"]
      int_name = log["app_type"]
    elif "service_id" in log:
      int_id = log["service_id"]
      int_name = log["service_type"]
    elif log["user_id"] == 0 and log["change_type"] == "removed":
      # No idea what these are, but they don't have any useful fields, so skip them.
      continue
    else:
      logger.warn("Unknown integration type: %s", log)
      continue
    if int_id not in integrations:
      integrations[int_id] = {"integration_name": int_name, "app_id": int_id, "status": status, "scopes": scopes, "user_id": log["user_id"], "user_name": log["user_name"], "date": log["date"]} 
      if "reason" in log:
        integrations[int_id]["reason"] = log["reason"]
      if "channel" in log:
        integrations[int_id]["channel"] = log["channel"]
  problem_integrations = []
  if "integration_issue_whitelist" in config:
    global_whitelist = config["integration_issue_whitelist"]
  else:
    global_whitelist = []
  for int_id in integrations:
    integration = integrations[int_id]
    if integration["status"] == "removed":
      continue
    if int_id in integration_whitelist:
      issue_whitelist = global_whitelist.extend(integration_whitelist[int_id])
    else:
      issue_whitelist = global_whitelist
    problems = []
    logger.debug("Checking for issues with integration: %s", integration)
    if "MAX" in integration["scopes"] and "legacy" not in issue_whitelist:
      problems.append("Legacy integration with full access to act as the user")
    if "admin" in integration["scopes"] and "admin" not in issue_whitelist:
      problems.append("Admin permission")
    if "chat:write:user" in integration["scopes"] and "chat:write:user" not in issue_whitelist:
      problems.append("Can chat as user")
    if "channels:history" in integration["scopes"] and "channels:history" not in issue_whitelist:
      problems.append("Can access channel history for public channels")
    if "files:read" in integration["scopes"] and "files:read" not in issue_whitelist:
      problems.append("Can read uploaded files")
    if "files:write:user" in integration["scopes"] and "files:write:user" not in issue_whitelist:
      problems.append("Can modify/delete existing files")
    if "groups:history" in integration["scopes"] and "groups:history" not in issue_whitelist:
      problems.append("Can access channel history for private channels")
    if "im:history" in integration["scopes"] and "im:history" not in issue_whitelist:
      problems.append("Can access channel history for private IMs")
    if "mpim:history" in integration["scopes"] and "mpim:history" not in issue_whitelist:
      problems.append("Can access channel history for multi-party IMs")
    if "pins:read" in integration["scopes"] and "pins:read" not in issue_whitelist:
      problems.append("Can access channel pinned messages/files")
    if "search:read" in integration["scopes"] and "search:read" not in issue_whitelist:
      problems.append("Can search team files and messages")
    if problems:
      integration["problems"] = problems
      problem_integrations.append(integration)
  return problem_integrations

def check_users(api_client, config):
  result = api_client.api_call("users.list", presence=False, limit=100)
  logger.debug("User list results: %s", result)
  if not result["ok"]:
    raise RuntimeError("API Call encountered an error while getting initial user list: "+unicode(result))
  users = result["members"]
  while "next_cursor" in result["response_metadata"] and result["response_metadata"]["next_cursor"]:
    logger.info("Further pages of users exist. Pulling next page...")
    result = api_client.api_call("users.list", presence=False, limit=100, cursor=result["response_metadata"]["next_cursor"])
    logger.debug("User list results: %s", result)
    if not result["ok"]:
      raise RuntimeError("API Call encountered an error while getting additional user list: "+unicode(result))
    users.extend(result["members"])
  problem_users = []
  retained_keys = ["real_name", "id", "team_id", "name", "problems", "has_2fa", "two_factor_type", "updated", "is_owner", "is_admin"]
  if "user_whitelist" in config:
    user_whitelist = config["user_whitelist"]
  else:
    user_whitelist = {}
  if "user_issue_whitelist" in config:
    global_whitelist = config["user_issue_whitelist"]
  else:
    global_whitelist = []
  for user in users:
    logger.debug("Checking for issues with user: %s", user)
    if user["id"] == "USLACKBOT":
      # Special case Slackbot, since it lacks the fields of other users/bots
      continue
    if user["deleted"] or user["is_bot"]:
      continue
    if user["id"] in user_whitelist:
      issue_whitelist = global_whitelist.extend(user_whitelist[user["id"]])
    else:
      issue_whitelist = global_whitelist
    if not user["has_2fa"] and "2fa" not in issue_whitelist:
      user["problems"] = ["User does not have 2FA enabled"]
    if user["has_2fa"] and user["two_factor_type"] == "sms" and "sms" not in issue_whitelist:
      user["problems"] = ["User is using less-secure SMS-based 2FA"]
    if "problems" in user:
      problem_user = {k:v for k,v in user.iteritems() if k in retained_keys}
      problem_users.append(problem_user)
  return problem_users



def notify_problems(problems, config, slack_bot, heading="Problems:", item_name="name", sort_field=None):
  indent = "\t"
  if "output_channel" in config:
    indent = "\t\t"
  if sort_field:
    problems = sorted(problems, key=lambda k: k[sort_field])
  prob_strings = []
  for problem in problems:
    fmt_problem = problem[item_name]+": "+", ".join(problem["problems"])
    for item in sorted(problem.items()):
      if not hasattr(item[1], "strip") and (hasattr(item[1], "__getitem__") or hasattr(item[1], "__iter__")):
        val = ", ".join(item[1])
      else:
        val = unicode(item[1])
      fmt_problem= fmt_problem+"\n"+indent+item[0]+": "+val
    prob_strings.append(fmt_problem)
  formatted_problems = "\n\n".join(prob_strings)
  if "output_channel" in config:
    if len(formatted_problems) < 3000:
      attachment = [{
        "fallback": heading+"\n"+formatted_problems,
        "title": heading,
        "text": formatted_problems,
        "color": "#ffe600"
      }]
      result = slack_bot.api_call("chat.postMessage", channel=config["output_channel"], attachments=attachment, as_user=True)
    else:
      # For bigger files we use a snippet. This has a 1MB limit. If you have more problems... well add that to the list.
      result = slack_bot.api_call("files.upload", content=formatted_problems, title=heading, filetype="text")
      logger.info("Message too large. Uploaded as file: %s", result)
      if not result["ok"]:
        raise RuntimeError("API Call encountered an error while uploading file: "+unicode(result))
      result = slack_bot.api_call("chat.postMessage", channel=config["output_channel"], text="*"+heading+"*\n\nToo many issues to post directly.\nSee <"+result["file"]["url_private"]+"|the uploaded file> for more information.", unfurl_links=True, as_user=True)
    logger.info("Message posted. Result: %s", result)
    if not result["ok"]:
      raise RuntimeError("API Call encountered an error while posting message: "+unicode(result))
  else:
    print heading
    print ""
    print formatted_problems


if __name__ == '__main__':
  parser = argparse.ArgumentParser(prog="Belay", description="Check the security of your Slack.")
  parser.add_argument("-c", "--config", default=None, help="Non-standard location of a configuration file.")
  parser.add_argument("-f", "--file", default=None,  help="File to redirect log output into.")
  parser.add_argument("-t", "--team", default=None, help="Team to check for multi-team configs.")
  parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase log verbosity level. (Default level: WARN, use twice for DEBUG)")
  parser.add_argument("-V", "--version", action="version", version="%(prog)s "+program_version, help="Display version information and exit.")
  args = parser.parse_args()
  loglevel = max(10, 30 - (args.verbose * 10))
  logformat = '%(asctime)s %(levelname)s: %(message)s'
  if args.file:
    logging.basicConfig(filename=args.file, level=loglevel, format=logformat)
  else:
    logging.basicConfig(level=loglevel, format=logformat)

  logger.info("Belaying...")
#  try:
  config = load_config(args.config, args.team)
  belay(config)
#  except Exception as e:
#    sys.exit(e)
#  finally:
  logging.shutdown()
