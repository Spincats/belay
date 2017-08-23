#!/usr/bin/env python

import sys
import os
import yaml
from slackclient import SlackClient

import pprint

# TODO: Logging Config, prints are just hack-y


# Try the usual places to store an API token
# First token wins
api_token = None
homedir = os.path.expanduser("~")
scriptdir = os.path.dirname(os.path.realpath(__file__))

# 1. Environment variables
if "SLACK_API_TOKEN" in os.environ:
  api_token = os.environ["SLACK_API_TOKEN"]
# 2. ~/.config/slack/config.yml
elif os.path.isfile(os.path.join(homedir,".config","slack","config.yml")):
  with open(os.path.join(homedir,".config","slack","config.yml"), "r") as config:
    config_data = yaml.load(config)
  api_token = config_data["api_token"]
# 3. ./config.yml
elif os.path.isfile(os.path.join(scriptdir,"config.yml")):
  with open(os.path.join(scriptdir,"config.yml"), "r") as config:
    config_data = yaml.load(config)
  api_token = config_data["api_token"]


if not api_token:
  print "ERROR: API token not found. Exiting."
  sys.exit(-1)

# Now to use that token on the API
slack = SlackClient(api_token)

result = slack.api_call("team.integrationLogs")
pp = pprint.PrettyPrinter(indent=4)
pp.pprint(result)
