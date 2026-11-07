"""InfoboxSweep: removes infobox requests from the talk pages of Wikipedia
articles that already have an infobox, through Pywikibot."""

__version__ = '0.1.0'

# The bot approval this task runs under, linked from every edit summary.
# Change it to the task's own request once it has one (or pass --brfa).
BRFA = 'Wikipedia:Bots/Requests for approval/ZackBot 15'

# The maintenance category whose whole tree of subcategories the bot goes
# through.
ROOT_CATEGORY = 'Category:Wikipedia articles with an infobox request'
