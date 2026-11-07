# Copy to user-config.py, in the directory you run the bot from or in
# PYWIKIBOT_DIR.  Live runs need it.  Dry runs work without it, but with it
# they also send User:ZackBot in the User-Agent, which Wikimedia asks for.
# Never commit user-config.py or user-password.py: .gitignore leaves them out.
family = 'wikipedia'
mylang = 'en'
usernames['wikipedia']['en'] = 'ZackBot'

# user-password.py contains one line, with a bot password made at
# https://en.wikipedia.org/wiki/Special:BotPasswords:
#   ('ZackBot', BotPassword('infoboxsweep', '<the password it gives you>'))
# Give it the "High-volume (bot) access" and "Edit existing pages" grants.
password_file = 'user-password.py'

put_throttle = 10   # seconds between edits, at least
