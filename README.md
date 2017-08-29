# belay

A simple python utility for checking up on your Slack organization.

## Setup

While belay can utilize legacy tokens with the `MAX` permission scope, stored in plaintext, and with everything installed system-wide, this goes against modern security and system administration practices. Instead of doing that, below we will go into depth to describe how to set up `belay` on a standard unix-like system.

### Python Environment

Depending on your choice of system, please use the package manager of your choice to install `python-2.7`, `pip`, and `virtualenv`. Now, selecting a directory that can host executable files, create a virtualenv for belay to run from

> $ virtualenv belayenv

Once that is complete, move into the new `belayenv` directory and activate your new virtual environment:

> $ . ./bin/activate

Now that we're in the environment, please download `belay` from your choice of source. For example:

> $(belayenv) git clone git@github.com:bobthesecurityguy/belay.git

Now move into that new directory and install `belay`'s (relatively short) list of requirements:

> $(belayenv) pip install -r requirements.txt

On certain systems, installing these dependencies from `pip` may fail. In that case, check your package manager for pre-built packages under that name and then re-run the above command until it succeeds.

### API Tokens

To create the required API tokens, direct your browser to the [Slack API Apps list](https://api.slack.com/apps) and (once signed-in to the appropriate team) click on the "Create New App" button. This should present you with a menu that allows you to set a name for the app (we recommend "Belay") and select the team to enable it on.

Once you enter that information, you will be taken to the detailed settings for your new app. Feel free to set the "Display Information" in a way that makes sense to you and ignore the "App Credentials" presented. Move down to "Bot Users", enable a bot user with the name of your choice, and then move back up to "OAuth & Permissions".

In the OAuth section select the following permissions. In an effort to make you a bit more comfortable with granting these, each will be listed with a full description of what we use it for below:

> admin            - Used to access integration logs.
> bot              - Used to act as the bot user.
> chat:write:bot   - Used to send messages as our bot.
> files:write:user - Used to upload messages as files if too large.
> users:read       - Used to access the user list.

Once you have granted those permissions, install the app and take note of the OAuth tokens that have been generated for you.

### Config File

The `belay` config file is a YAML config file that allows you to configure most settings within the script. Some settings are available at the command line (mostly runtime options like verbosity and log output file) and some can be pulled in from the environment (the OAuth tokens). (Note that securely getting those tokens into the environment without placing them on disk is outside the scope of this document. For simplicity, this description will assume that they are in the config file.)

The config file can be placed anywhere, but if a location is not given at runtime, the script will default to looking in `~/.config/belay/config.yml` or `./config.yml` in that order for the config. If the OAuth tokens are in the environment, it is possible to run without a config file, but most uses will want to set one up.

The format of the config file is standard YAML formatting. If only one team is to be audited, the top-level "teams" dictionary may be omitted as may the outer wrapper dictionary for the team in question.

Within a team dictionary, the following keys are valid and may have the following values:

> api\_token                    - A string token
> bot\_token                    - A string token
> skip\_integrations            - A boolean that skips the audit of active integrations
> integration\_whitelist        - A dictionary (key=integration\_id) of lists of issues to ignore
> integration\_issue\_whitelist - A list of issues to ignore
> user\_whitelist               - A dictionary (key=id) of lists of issues to ignore
> user\_issue\_whitelist        - A list of issues to ignore
> output\_channel               - The Slack channel name in which to output our results

Possible values for the issues with integrations are:

> legacy
> admin
> chat:write:user
> channels:history
> files:read
> files:write:user
> groups:history
> im:history
> mpim:history
> pins:read
> search:read

Possible values for the issues with users are:

> 2fa
> sms

An example of how one might construct an actual working configuration from this is included in `example.yml`.

## Output

It is recommended to run Belay with the verbose flag and redirecting output to a file until you are certain that the configuration is correct. This is usually sufficient to identify issues with your configuration. Debug mode (`-vv`) logs an excessive amount of information and may log sensitve information and should be used with care.

Please note that, when interpreting output from this program, some integrations really do need the permissions that we flag as potentially dangerous. Even `belay` needs some of the permissions on the list. The output of this program is not intended as a checklist of integrations for removal. Rather, it is intended to bring to light applications requesting sensitive permissions. If these permissions do not make sense for that application, it may be worth further investigation.

Similarly, the use of SMS-based 2FA in many organizations is not a sufficient risk to justify concerted eradication efforts. Please use reasonable judgment when interpreting the output of `belay`.

## Changelog

* 1.0 - Initial public release
    * Checks for integrations with sensitive permissions
    * Checks for users with no 2FA or with SMS-based 2FA
    * Fully documented
