"""InfoboxSweep: removes infobox requests from the talk pages of Wikipedia
articles that already have an infobox, and photograph requests from those
of articles that already have a photograph, through Pywikibot."""

__version__ = '0.1.0'

# The bot approvals the tasks run under, linked from every edit summary.
# Change them to the tasks' own requests once they have them (or pass --brfa).
BRFA = 'Wikipedia:Bots/Requests for approval/ZackBot 15'          # infoboxsweep
PHOTO_BRFA = 'Wikipedia:Bots/Requests for approval/ZackBot 16'    # imagesweep

# The maintenance categories whose whole trees of subcategories the tasks go
# through.
ROOT_CATEGORY = 'Category:Wikipedia articles with an infobox request'
PHOTO_CATEGORY = 'Category:Wikipedia requested photographs'
