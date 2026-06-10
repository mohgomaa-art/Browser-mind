"""
BrowserMind — 500 Target Websites
====================================
Organized by subagent domain.
Used by TrainingCoordinator to feed SubAgents.

Usage:
    from training.target_websites import get_tasks_for_domain, ALL_WEBSITE_TASKS
    extract_tasks   = get_tasks_for_domain("extract")
    nav_tasks       = get_tasks_for_domain("navigation")
    all_tasks       = [(t["goal"], t["url"]) for t in ALL_WEBSITE_TASKS]
"""

from typing import List, Dict, Tuple


ALL_WEBSITE_TASKS: List[Dict] = [

    # ──────────────────────────────────────────────
    #  SEARCH ENGINES (domain: search)
    # ──────────────────────────────────────────────
    {"url": "https://www.google.com",              "domain": "search", "goal": "search for python tutorials",                    "action_type": "type",    "difficulty": 1},
    {"url": "https://www.bing.com",                "domain": "search", "goal": "search for machine learning news",               "action_type": "type",    "difficulty": 1},
    {"url": "https://duckduckgo.com",              "domain": "search", "goal": "search for open source projects",                "action_type": "type",    "difficulty": 1},
    {"url": "https://scholar.google.com",          "domain": "search", "goal": "search for deep learning papers 2024",          "action_type": "type",    "difficulty": 2},
    {"url": "https://www.google.com/maps",         "domain": "search", "goal": "search for coffee shops nearby",                "action_type": "type",    "difficulty": 2},
    {"url": "https://search.yahoo.com",            "domain": "search", "goal": "search for latest tech news",                   "action_type": "type",    "difficulty": 1},
    {"url": "https://www.wolframalpha.com",        "domain": "search", "goal": "calculate integral of x squared",               "action_type": "type",    "difficulty": 2},
    {"url": "https://www.ecosia.org",              "domain": "search", "goal": "search for renewable energy news",              "action_type": "type",    "difficulty": 1},
    {"url": "https://search.brave.com",            "domain": "search", "goal": "search for privacy tools",                      "action_type": "type",    "difficulty": 1},
    {"url": "https://yandex.com",                  "domain": "search", "goal": "search for artificial intelligence",            "action_type": "type",    "difficulty": 1},

    # ──────────────────────────────────────────────
    #  SOCIAL MEDIA (domain: social)
    # ──────────────────────────────────────────────
    {"url": "https://twitter.com/explore",         "domain": "social", "goal": "extract trending topics and hashtags",          "action_type": "extract", "difficulty": 4},
    {"url": "https://www.reddit.com",              "domain": "social", "goal": "extract top post titles from front page",       "action_type": "extract", "difficulty": 1},
    {"url": "https://www.reddit.com/r/programming","domain": "social", "goal": "extract top 10 post titles and scores",         "action_type": "extract", "difficulty": 1},
    {"url": "https://www.reddit.com/r/MachineLearning","domain":"social","goal":"extract post titles about new AI models",      "action_type": "extract", "difficulty": 2},
    {"url": "https://www.reddit.com/r/webdev",     "domain": "social", "goal": "extract trending web development posts",        "action_type": "extract", "difficulty": 1},
    {"url": "https://www.linkedin.com/feed",       "domain": "social", "goal": "extract visible post headlines",               "action_type": "extract", "difficulty": 4},
    {"url": "https://www.linkedin.com/jobs",       "domain": "social", "goal": "extract all job titles and companies",          "action_type": "extract", "difficulty": 4},
    {"url": "https://www.producthunt.com",         "domain": "social", "goal": "extract top product names and taglines today",  "action_type": "extract", "difficulty": 2},
    {"url": "https://www.devto.com",               "domain": "social", "goal": "extract article titles from the feed",         "action_type": "extract", "difficulty": 1},
    {"url": "https://dev.to",                      "domain": "social", "goal": "extract top 5 article titles and tags",         "action_type": "extract", "difficulty": 1},
    {"url": "https://hashnode.com",                "domain": "social", "goal": "extract recent blog post titles",               "action_type": "extract", "difficulty": 1},
    {"url": "https://lobste.rs",                   "domain": "social", "goal": "extract story titles and point counts",         "action_type": "extract", "difficulty": 1},
    {"url": "https://www.pinterest.com",           "domain": "social", "goal": "scroll down and extract visible pin titles",    "action_type": "scroll",  "difficulty": 2},
    {"url": "https://www.quora.com",               "domain": "social", "goal": "extract top question titles on the page",       "action_type": "extract", "difficulty": 2},
    {"url": "https://www.tumblr.com",              "domain": "social", "goal": "scroll and extract visible post text",          "action_type": "scroll",  "difficulty": 2},
    {"url": "https://www.instagram.com/explore",   "domain": "social", "goal": "navigate to explore page",                     "action_type": "navigate","difficulty": 4},
    {"url": "https://www.snapchat.com",            "domain": "social", "goal": "navigate to the main page and extract links",   "action_type": "navigate","difficulty": 2},

    # ──────────────────────────────────────────────
    #  NEWS (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://news.ycombinator.com",        "domain": "extract","goal": "extract top 10 story titles and scores",         "action_type": "extract", "difficulty": 1},
    {"url": "https://techcrunch.com",              "domain": "extract","goal": "extract all article headlines from the page",    "action_type": "extract", "difficulty": 1},
    {"url": "https://www.theverge.com",            "domain": "extract","goal": "extract article titles from the front page",     "action_type": "extract", "difficulty": 1},
    {"url": "https://arstechnica.com",             "domain": "extract","goal": "extract article headlines and authors",          "action_type": "extract", "difficulty": 1},
    {"url": "https://www.wired.com",               "domain": "extract","goal": "extract story titles from the front page",       "action_type": "extract", "difficulty": 1},
    {"url": "https://www.bbc.com/news",            "domain": "extract","goal": "extract all news headlines",                    "action_type": "extract", "difficulty": 1},
    {"url": "https://www.cnn.com",                 "domain": "extract","goal": "extract breaking news headlines",               "action_type": "extract", "difficulty": 1},
    {"url": "https://www.reuters.com",             "domain": "extract","goal": "extract top news story titles",                 "action_type": "extract", "difficulty": 1},
    {"url": "https://apnews.com",                  "domain": "extract","goal": "extract all article titles on the page",        "action_type": "extract", "difficulty": 1},
    {"url": "https://www.aljazeera.com",           "domain": "extract","goal": "extract news headlines from the front page",    "action_type": "extract", "difficulty": 1},
    {"url": "https://www.theguardian.com",         "domain": "extract","goal": "extract all article titles",                   "action_type": "extract", "difficulty": 1},
    {"url": "https://www.nytimes.com",             "domain": "extract","goal": "extract visible article headlines",             "action_type": "extract", "difficulty": 2},
    {"url": "https://www.washingtonpost.com",      "domain": "extract","goal": "extract article titles from front page",        "action_type": "extract", "difficulty": 2},
    {"url": "https://www.bloomberg.com",           "domain": "extract","goal": "extract financial news headlines",              "action_type": "extract", "difficulty": 2},
    {"url": "https://www.ft.com",                  "domain": "extract","goal": "extract article titles from the page",          "action_type": "extract", "difficulty": 2},
    {"url": "https://www.economist.com",           "domain": "extract","goal": "extract article titles and sections",           "action_type": "extract", "difficulty": 2},
    {"url": "https://www.nature.com/news",         "domain": "extract","goal": "extract science news headlines",               "action_type": "extract", "difficulty": 1},
    {"url": "https://www.sciencedaily.com",        "domain": "extract","goal": "extract all science article titles",            "action_type": "extract", "difficulty": 1},
    {"url": "https://www.technologyreview.com",    "domain": "extract","goal": "extract article titles from the front page",    "action_type": "extract", "difficulty": 1},
    {"url": "https://www.zdnet.com",               "domain": "extract","goal": "extract technology news headlines",             "action_type": "extract", "difficulty": 1},
    {"url": "https://venturebeat.com",             "domain": "extract","goal": "extract AI and tech article titles",            "action_type": "extract", "difficulty": 1},
    {"url": "https://www.infoq.com",               "domain": "extract","goal": "extract article titles and topics",             "action_type": "extract", "difficulty": 1},
    {"url": "https://slashdot.org",                "domain": "extract","goal": "extract story titles and comment counts",       "action_type": "extract", "difficulty": 1},

    # ──────────────────────────────────────────────
    #  VIDEO / MEDIA (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.youtube.com/feed/trending","domain":"extract","goal": "extract all trending video titles and channels", "action_type": "extract", "difficulty": 1},
    {"url": "https://www.youtube.com",             "domain": "extract","goal": "scroll down and extract recommended video titles","action_type":"scroll",  "difficulty": 1},
    {"url": "https://vimeo.com/explore",           "domain": "extract","goal": "extract featured video titles",                 "action_type": "extract", "difficulty": 1},
    {"url": "https://www.twitch.tv/directory",     "domain": "extract","goal": "extract top live stream titles and viewer counts","action_type":"extract","difficulty": 2},
    {"url": "https://rumble.com",                  "domain": "extract","goal": "extract trending video titles",                 "action_type": "extract", "difficulty": 1},
    {"url": "https://odysee.com",                  "domain": "extract","goal": "extract featured content titles",               "action_type": "extract", "difficulty": 1},
    {"url": "https://www.dailymotion.com",         "domain": "extract","goal": "extract trending video titles from the page",   "action_type": "extract", "difficulty": 1},
    {"url": "https://podcasts.apple.com/us/top-podcasts","domain":"extract","goal":"extract top podcast names and categories",  "action_type": "extract", "difficulty": 2},
    {"url": "https://open.spotify.com/genre/toplists","domain":"extract","goal":"extract top playlist names",                  "action_type": "extract", "difficulty": 2},

    # ──────────────────────────────────────────────
    #  DEVELOPER / CODE (domain: navigation)
    # ──────────────────────────────────────────────
    {"url": "https://github.com/trending",         "domain": "navigation","goal":"extract all trending repository names and stars","action_type":"extract","difficulty":1},
    {"url": "https://github.com/explore",          "domain": "navigation","goal":"extract featured repository names",           "action_type": "extract", "difficulty": 1},
    {"url": "https://github.com/topics/python",    "domain": "navigation","goal":"extract repository names in python topic",    "action_type": "extract", "difficulty": 1},
    {"url": "https://github.com/topics/machine-learning","domain":"navigation","goal":"extract ML repository names and descriptions","action_type":"extract","difficulty":1},
    {"url": "https://github.com/about",            "domain": "navigation","goal":"navigate to about page and extract key stats","action_type":"navigate", "difficulty":1},
    {"url": "https://gitlab.com/explore",          "domain": "navigation","goal":"extract featured project names",              "action_type": "extract", "difficulty": 1},
    {"url": "https://bitbucket.org",               "domain": "navigation","goal":"navigate to main page and extract links",     "action_type": "navigate","difficulty": 1},
    {"url": "https://stackoverflow.com/questions", "domain": "navigation","goal":"extract top question titles and vote counts", "action_type": "extract", "difficulty": 1},
    {"url": "https://stackoverflow.com/jobs",      "domain": "navigation","goal":"extract job titles and company names",        "action_type": "extract", "difficulty": 1},
    {"url": "https://stackexchange.com",           "domain": "navigation","goal":"extract top community names and stats",       "action_type": "extract", "difficulty": 1},
    {"url": "https://www.npmjs.com",               "domain": "navigation","goal":"search for react and extract top packages",   "action_type": "type",    "difficulty": 1},
    {"url": "https://pypi.org",                    "domain": "navigation","goal":"search for requests package and extract info","action_type": "type",    "difficulty": 1},
    {"url": "https://crates.io",                   "domain": "navigation","goal":"extract most downloaded crate names",         "action_type": "extract", "difficulty": 1},
    {"url": "https://packagist.org",               "domain": "navigation","goal":"extract popular PHP package names",           "action_type": "extract", "difficulty": 1},
    {"url": "https://rubygems.org",                "domain": "navigation","goal":"extract most downloaded gem names",           "action_type": "extract", "difficulty": 1},
    {"url": "https://hub.docker.com/search",       "domain": "navigation","goal":"search for python and extract official images","action_type":"type",   "difficulty": 1},
    {"url": "https://www.dockerhub.com",           "domain": "navigation","goal":"navigate to explore page",                   "action_type": "navigate","difficulty": 1},
    {"url": "https://colab.research.google.com",   "domain": "navigation","goal":"navigate to new notebook button",            "action_type": "navigate","difficulty": 2},
    {"url": "https://replit.com/explore",          "domain": "navigation","goal":"extract featured project titles",             "action_type": "extract", "difficulty": 1},
    {"url": "https://codepen.io/trending",         "domain": "navigation","goal":"extract trending pen titles and authors",     "action_type": "extract", "difficulty": 1},
    {"url": "https://jsfiddle.net",                "domain": "navigation","goal":"navigate to main page and extract sections",  "action_type": "navigate","difficulty": 1},
    {"url": "https://www.hackerrank.com/challenges","domain":"navigation","goal":"extract challenge names and difficulty levels","action_type":"extract","difficulty":2},
    {"url": "https://leetcode.com/problemset",     "domain": "navigation","goal":"extract problem titles and acceptance rates", "action_type": "extract", "difficulty": 2},
    {"url": "https://www.codewars.com/kata/latest","domain":"navigation","goal":"extract kata names and difficulty ranks",      "action_type": "extract", "difficulty": 2},
    {"url": "https://exercism.org/tracks",         "domain": "navigation","goal":"extract all programming language track names","action_type":"extract",  "difficulty": 1},
    {"url": "https://www.geeksforgeeks.org",       "domain": "navigation","goal":"extract article titles from the front page",  "action_type": "extract", "difficulty": 1},
    {"url": "https://www.w3schools.com",           "domain": "navigation","goal":"extract all tutorial category names",         "action_type": "extract", "difficulty": 1},
    {"url": "https://developer.mozilla.org/en-US", "domain": "navigation","goal":"extract featured documentation titles",       "action_type": "extract", "difficulty": 1},
    {"url": "https://docs.python.org/3",           "domain": "navigation","goal":"extract all documentation section names",     "action_type": "extract", "difficulty": 1},
    {"url": "https://docs.python.org/3/library",   "domain": "navigation","goal":"extract standard library module names",       "action_type": "extract", "difficulty": 1},
    {"url": "https://pytorch.org/docs/stable",     "domain": "navigation","goal":"extract documentation category names",        "action_type": "extract", "difficulty": 1},
    {"url": "https://www.tensorflow.org/api_docs", "domain": "navigation","goal":"extract API module names from the page",      "action_type": "extract", "difficulty": 1},
    {"url": "https://numpy.org/doc/stable",        "domain": "navigation","goal":"extract numpy documentation section names",   "action_type": "extract", "difficulty": 1},
    {"url": "https://pandas.pydata.org/docs",      "domain": "navigation","goal":"extract pandas documentation titles",         "action_type": "extract", "difficulty": 1},
    {"url": "https://scikit-learn.org/stable",     "domain": "navigation","goal":"extract module and class names from docs",    "action_type": "extract", "difficulty": 1},
    {"url": "https://huggingface.co/models",       "domain": "navigation","goal":"extract top model names and download counts", "action_type": "extract", "difficulty": 1},
    {"url": "https://huggingface.co/datasets",     "domain": "navigation","goal":"extract popular dataset names and sizes",     "action_type": "extract", "difficulty": 1},
    {"url": "https://paperswithcode.com",          "domain": "navigation","goal":"extract paper titles and benchmark scores",   "action_type": "extract", "difficulty": 2},
    {"url": "https://arxiv.org/list/cs.AI/recent", "domain": "navigation","goal":"extract recent AI paper titles",              "action_type": "extract", "difficulty": 1},
    {"url": "https://arxiv.org/search",            "domain": "navigation","goal":"search for transformer architecture papers",  "action_type": "type",    "difficulty": 1},
    {"url": "https://www.kaggle.com/competitions", "domain": "navigation","goal":"extract competition names and prize amounts",  "action_type": "extract", "difficulty": 2},
    {"url": "https://www.kaggle.com/datasets",     "domain": "navigation","goal":"extract popular dataset names and sizes",     "action_type": "extract", "difficulty": 1},
    {"url": "https://mlflow.org",                  "domain": "navigation","goal":"navigate to documentation page",              "action_type": "navigate","difficulty": 1},
    {"url": "https://wandb.ai/gallery",            "domain": "navigation","goal":"extract featured project names",              "action_type": "extract", "difficulty": 2},

    # ──────────────────────────────────────────────
    #  E-COMMERCE (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.amazon.com/best-sellers",  "domain":"extract","goal":"extract product names and prices from best sellers","action_type":"extract","difficulty":1},
    {"url": "https://www.amazon.com/deals",         "domain":"extract","goal":"extract deal product names and discount percentages","action_type":"extract","difficulty":2},
    {"url": "https://www.ebay.com/deals",           "domain":"extract","goal":"extract deal names and prices",                  "action_type":"extract","difficulty":1},
    {"url": "https://www.etsy.com/trending",        "domain":"extract","goal":"extract trending product names and prices",       "action_type":"extract","difficulty":2},
    {"url": "https://www.aliexpress.com",           "domain":"extract","goal":"extract featured product names and prices",       "action_type":"extract","difficulty":2},
    {"url": "https://www.walmart.com/deals",        "domain":"extract","goal":"extract deal product names and prices",           "action_type":"extract","difficulty":1},
    {"url": "https://www.target.com/deals",         "domain":"extract","goal":"extract deal names and discount amounts",         "action_type":"extract","difficulty":1},
    {"url": "https://www.bestbuy.com/site/electronics","domain":"extract","goal":"extract electronics product names and prices", "action_type":"extract","difficulty":1},
    {"url": "https://store.steampowered.com/specials","domain":"extract","goal":"extract game names and discount percentages",   "action_type":"extract","difficulty":1},
    {"url": "https://www.newegg.com/todays-deals",  "domain":"extract","goal":"extract tech product names and prices",           "action_type":"extract","difficulty":1},
    {"url": "https://www.shopify.com",              "domain":"navigation","goal":"navigate to pricing page and extract plans",   "action_type":"navigate","difficulty":1},
    {"url": "https://www.noon.com",                 "domain":"extract","goal":"extract featured product names and prices",       "action_type":"extract","difficulty":1},
    {"url": "https://www.jumia.com",                "domain":"extract","goal":"extract flash sale product names and prices",     "action_type":"extract","difficulty":2},

    # ──────────────────────────────────────────────
    #  EDUCATION / COURSES (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.coursera.org",             "domain":"extract","goal":"extract featured course names and institutions",  "action_type":"extract","difficulty":1},
    {"url": "https://www.udemy.com",                "domain":"extract","goal":"extract top course names and ratings",            "action_type":"extract","difficulty":1},
    {"url": "https://www.edx.org",                  "domain":"extract","goal":"extract featured program names",                 "action_type":"extract","difficulty":1},
    {"url": "https://www.khanacademy.org",          "domain":"navigation","goal":"extract all subject names from the page",      "action_type":"extract","difficulty":1},
    {"url": "https://www.pluralsight.com/browse",   "domain":"extract","goal":"extract course category names",                  "action_type":"extract","difficulty":1},
    {"url": "https://www.skillshare.com",           "domain":"extract","goal":"extract featured class names and teachers",       "action_type":"extract","difficulty":2},
    {"url": "https://brilliant.org",                "domain":"navigation","goal":"extract available course names",               "action_type":"extract","difficulty":1},
    {"url": "https://www.duolingo.com",             "domain":"navigation","goal":"navigate to courses page and extract language names","action_type":"navigate","difficulty":1},
    {"url": "https://www.codecademy.com/catalog",   "domain":"extract","goal":"extract all course and path names",              "action_type":"extract","difficulty":1},
    {"url": "https://www.freecodecamp.org",         "domain":"extract","goal":"extract certification names from the page",       "action_type":"extract","difficulty":1},
    {"url": "https://www.theodinproject.com",       "domain":"navigation","goal":"extract curriculum path names",               "action_type":"extract","difficulty":1},
    {"url": "https://ocw.mit.edu",                  "domain":"extract","goal":"extract featured course names and departments",   "action_type":"extract","difficulty":1},
    {"url": "https://www.fast.ai",                  "domain":"extract","goal":"extract course names and lesson titles",          "action_type":"extract","difficulty":1},
    {"url": "https://www.deeplearning.ai",          "domain":"extract","goal":"extract specialization names and course counts",  "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  CLOUD & DEVOPS (domain: navigation)
    # ──────────────────────────────────────────────
    {"url": "https://aws.amazon.com/products",      "domain":"navigation","goal":"extract all AWS product category names",       "action_type":"extract","difficulty":1},
    {"url": "https://cloud.google.com/products",    "domain":"navigation","goal":"extract Google Cloud product names",           "action_type":"extract","difficulty":1},
    {"url": "https://azure.microsoft.com/en-us/products","domain":"navigation","goal":"extract Azure service names",            "action_type":"extract","difficulty":1},
    {"url": "https://www.digitalocean.com/products","domain":"navigation","goal":"extract product names and starting prices",    "action_type":"extract","difficulty":1},
    {"url": "https://www.heroku.com",               "domain":"navigation","goal":"navigate to pricing page",                    "action_type":"navigate","difficulty":1},
    {"url": "https://vercel.com",                   "domain":"navigation","goal":"navigate to pricing page and extract plan names","action_type":"navigate","difficulty":1},
    {"url": "https://www.cloudflare.com/products",  "domain":"navigation","goal":"extract all product names",                   "action_type":"extract","difficulty":1},
    {"url": "https://render.com",                   "domain":"navigation","goal":"navigate to pricing page",                    "action_type":"navigate","difficulty":1},
    {"url": "https://railway.app",                  "domain":"navigation","goal":"navigate to pricing and extract plan names",   "action_type":"navigate","difficulty":1},
    {"url": "https://www.linode.com/pricing",       "domain":"navigation","goal":"extract plan names and prices",               "action_type":"extract","difficulty":1},
    {"url": "https://www.vultr.com/products",       "domain":"navigation","goal":"extract cloud product names and prices",       "action_type":"extract","difficulty":1},
    {"url": "https://supabase.com",                 "domain":"navigation","goal":"navigate to pricing page and extract features","action_type":"navigate","difficulty":1},
    {"url": "https://firebase.google.com",          "domain":"navigation","goal":"extract Firebase product names",              "action_type":"extract","difficulty":1},
    {"url": "https://www.mongodb.com/cloud",        "domain":"navigation","goal":"extract cloud service names",                 "action_type":"extract","difficulty":1},
    {"url": "https://planetscale.com/pricing",      "domain":"navigation","goal":"extract pricing plan names and limits",        "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  AI TOOLS (domain: navigation)
    # ──────────────────────────────────────────────
    {"url": "https://openai.com",                   "domain":"navigation","goal":"navigate to API page and extract model names", "action_type":"navigate","difficulty":1},
    {"url": "https://openai.com/pricing",           "domain":"extract", "goal":"extract model names and pricing tiers",          "action_type":"extract","difficulty":1},
    {"url": "https://anthropic.com",                "domain":"navigation","goal":"navigate to Claude page and extract features",  "action_type":"navigate","difficulty":1},
    {"url": "https://www.perplexity.ai",            "domain":"navigation","goal":"search for AI tools and extract results",       "action_type":"type",   "difficulty":2},
    {"url": "https://midjourney.com",               "domain":"navigation","goal":"navigate to main page and extract sections",    "action_type":"navigate","difficulty":2},
    {"url": "https://stability.ai",                 "domain":"navigation","goal":"extract AI product names",                     "action_type":"extract","difficulty":1},
    {"url": "https://replicate.com/explore",        "domain":"navigation","goal":"extract featured model names and run counts",   "action_type":"extract","difficulty":1},
    {"url": "https://civitai.com",                  "domain":"navigation","goal":"extract top model names and download counts",   "action_type":"extract","difficulty":2},
    {"url": "https://www.together.ai",              "domain":"navigation","goal":"extract available model names",                "action_type":"extract","difficulty":1},
    {"url": "https://groq.com",                     "domain":"navigation","goal":"navigate to playground page",                  "action_type":"navigate","difficulty":1},
    {"url": "https://ollama.com/library",           "domain":"navigation","goal":"extract all available model names and sizes",   "action_type":"extract","difficulty":1},
    {"url": "https://lmstudio.ai",                  "domain":"navigation","goal":"navigate to models page",                      "action_type":"navigate","difficulty":1},

    # ──────────────────────────────────────────────
    #  JOBS / FREELANCE (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.upwork.com/freelance-jobs","domain":"extract","goal":"extract job titles and hourly rates",              "action_type":"extract","difficulty":2},
    {"url": "https://www.fiverr.com",               "domain":"extract","goal":"extract featured gig titles and starting prices",  "action_type":"extract","difficulty":1},
    {"url": "https://www.toptal.com",               "domain":"navigation","goal":"navigate to hire page and extract skill names", "action_type":"navigate","difficulty":1},
    {"url": "https://angel.co/jobs",                "domain":"extract","goal":"extract startup job titles and companies",          "action_type":"extract","difficulty":2},
    {"url": "https://www.glassdoor.com/Job",        "domain":"extract","goal":"extract job titles and company names",             "action_type":"extract","difficulty":2},
    {"url": "https://www.indeed.com",               "domain":"forms",  "goal":"search for software engineer jobs and extract titles","action_type":"type","difficulty":1},
    {"url": "https://remoteok.com",                 "domain":"extract","goal":"extract remote job titles and companies",           "action_type":"extract","difficulty":1},
    {"url": "https://weworkremotely.com",           "domain":"extract","goal":"extract remote job category names and counts",      "action_type":"extract","difficulty":1},
    {"url": "https://wellfound.com/jobs",           "domain":"extract","goal":"extract startup job titles and locations",          "action_type":"extract","difficulty":2},
    {"url": "https://www.simplyhired.com",          "domain":"forms",  "goal":"search for data scientist and extract results",    "action_type":"type",   "difficulty":1},
    {"url": "https://www.bayt.com",                 "domain":"extract","goal":"extract job titles and company names",             "action_type":"extract","difficulty":1},
    {"url": "https://www.naukri.com",               "domain":"extract","goal":"extract featured job titles and companies",         "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  FORMS / REGISTRATION (domain: forms)
    # ──────────────────────────────────────────────
    {"url": "https://httpbin.org/forms/post",       "domain":"forms","goal":"fill contact form with name email and message fields","action_type":"type",   "difficulty":1},
    {"url": "https://www.wikipedia.org",            "domain":"forms","goal":"search for artificial intelligence and extract intro","action_type":"type",  "difficulty":1},
    {"url": "https://github.com/login",             "domain":"forms","goal":"locate username and password fields",                "action_type":"click",  "difficulty":1},
    {"url": "https://gitlab.com/users/sign_in",     "domain":"forms","goal":"locate login form fields",                          "action_type":"click",  "difficulty":1},
    {"url": "https://accounts.google.com",          "domain":"forms","goal":"locate email input field",                          "action_type":"click",  "difficulty":1},
    {"url": "https://login.microsoftonline.com",    "domain":"forms","goal":"locate email input and next button",                 "action_type":"click",  "difficulty":1},
    {"url": "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_form_submit","domain":"forms","goal":"fill form name and email fields and click submit","action_type":"type","difficulty":1},
    {"url": "https://formsmarts.com/html-form-example","domain":"forms","goal":"fill all form fields and submit",                 "action_type":"type",   "difficulty":2},
    {"url": "https://www.selenium.dev/selenium/web/web-form.html","domain":"forms","goal":"fill text input and submit button",   "action_type":"type",   "difficulty":1},
    {"url": "https://demoqa.com/automation-practice-form","domain":"forms","goal":"fill first name last name and email fields",  "action_type":"type",   "difficulty":2},
    {"url": "https://testpages.herokuapp.com/styled/basic-html-form-test.html","domain":"forms","goal":"fill username password and submit","action_type":"type","difficulty":1},
    {"url": "https://the-internet.herokuapp.com/login","domain":"forms","goal":"type username and password in login form",       "action_type":"type",   "difficulty":1},
    {"url": "https://practice.expandtesting.com/login","domain":"forms","goal":"fill login form with credentials",               "action_type":"type",   "difficulty":1},
    {"url": "https://mail.google.com",              "domain":"forms","goal":"click compose button to create new email",           "action_type":"click",  "difficulty":2},
    {"url": "https://mail.yahoo.com",               "domain":"forms","goal":"click compose button to write new email",            "action_type":"click",  "difficulty":2},

    # ──────────────────────────────────────────────
    #  FINANCE (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://finance.yahoo.com",            "domain":"extract","goal":"extract stock market index values",                "action_type":"extract","difficulty":1},
    {"url": "https://www.marketwatch.com",          "domain":"extract","goal":"extract top market movers and percentage changes", "action_type":"extract","difficulty":2},
    {"url": "https://coinmarketcap.com",            "domain":"extract","goal":"extract top 10 cryptocurrency names and prices",   "action_type":"extract","difficulty":1},
    {"url": "https://www.coingecko.com",            "domain":"extract","goal":"extract top coin names and 24h price changes",     "action_type":"extract","difficulty":1},
    {"url": "https://www.tradingview.com/markets",  "domain":"extract","goal":"extract market index names and values",            "action_type":"extract","difficulty":2},
    {"url": "https://www.investing.com",            "domain":"extract","goal":"extract top stock names and price changes",        "action_type":"extract","difficulty":2},
    {"url": "https://www.wsj.com/market-data",      "domain":"extract","goal":"extract market data headlines",                   "action_type":"extract","difficulty":2},
    {"url": "https://stockanalysis.com/stocks",     "domain":"extract","goal":"extract top stock names and market caps",          "action_type":"extract","difficulty":1},
    {"url": "https://finviz.com",                   "domain":"extract","goal":"extract top performing stock tickers and changes", "action_type":"extract","difficulty":2},

    # ──────────────────────────────────────────────
    #  PRODUCTIVITY / TOOLS (domain: navigation)
    # ──────────────────────────────────────────────
    {"url": "https://notion.so",                    "domain":"navigation","goal":"navigate to templates page and extract category names","action_type":"navigate","difficulty":2},
    {"url": "https://www.figma.com/community",      "domain":"navigation","goal":"extract featured template names",               "action_type":"extract","difficulty":2},
    {"url": "https://trello.com",                   "domain":"navigation","goal":"navigate to pricing page and extract plan names","action_type":"navigate","difficulty":1},
    {"url": "https://asana.com/pricing",            "domain":"navigation","goal":"extract plan names and feature counts",         "action_type":"extract","difficulty":1},
    {"url": "https://slack.com/pricing",            "domain":"navigation","goal":"extract plan names and prices",                 "action_type":"extract","difficulty":1},
    {"url": "https://zoom.us/pricing",              "domain":"navigation","goal":"extract plan names and monthly prices",         "action_type":"extract","difficulty":1},
    {"url": "https://www.dropbox.com/plans",        "domain":"navigation","goal":"extract storage plan names and prices",         "action_type":"extract","difficulty":1},
    {"url": "https://www.atlassian.com/software",   "domain":"navigation","goal":"extract product names from the page",           "action_type":"extract","difficulty":1},
    {"url": "https://linear.app",                   "domain":"navigation","goal":"navigate to pricing and extract plan names",    "action_type":"navigate","difficulty":1},
    {"url": "https://basecamp.com",                 "domain":"navigation","goal":"navigate to pricing page",                      "action_type":"navigate","difficulty":1},
    {"url": "https://www.airtable.com/pricing",     "domain":"navigation","goal":"extract plan names and limits",                 "action_type":"extract","difficulty":1},
    {"url": "https://zapier.com/pricing",           "domain":"navigation","goal":"extract automation plan names and task limits",  "action_type":"extract","difficulty":1},
    {"url": "https://make.com/en/pricing",          "domain":"navigation","goal":"extract plan names and operation counts",        "action_type":"extract","difficulty":1},
    {"url": "https://n8n.io/pricing",               "domain":"navigation","goal":"extract plan names and feature differences",     "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  SCIENCE / RESEARCH (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.nature.com",               "domain":"extract","goal":"extract featured journal article titles",           "action_type":"extract","difficulty":1},
    {"url": "https://science.sciencemag.org",       "domain":"extract","goal":"extract current issue article titles",             "action_type":"extract","difficulty":1},
    {"url": "https://www.cell.com",                 "domain":"extract","goal":"extract article titles from current issue",         "action_type":"extract","difficulty":1},
    {"url": "https://www.pnas.org",                 "domain":"extract","goal":"extract recent article titles",                    "action_type":"extract","difficulty":1},
    {"url": "https://www.sciencedirect.com",        "domain":"extract","goal":"extract featured article titles",                  "action_type":"extract","difficulty":1},
    {"url": "https://www.semanticscholar.org",      "domain":"forms",  "goal":"search for attention mechanism paper",             "action_type":"type",   "difficulty":1},
    {"url": "https://pubmed.ncbi.nlm.nih.gov",      "domain":"forms",  "goal":"search for machine learning in medicine",          "action_type":"type",   "difficulty":1},
    {"url": "https://ieeexplore.ieee.org",          "domain":"forms",  "goal":"search for deep learning survey papers",           "action_type":"type",   "difficulty":1},

    # ──────────────────────────────────────────────
    #  GOVERNMENT / REFERENCE (domain: navigation)
    # ──────────────────────────────────────────────
    {"url": "https://www.who.int",                  "domain":"navigation","goal":"navigate to health topics and extract category names","action_type":"navigate","difficulty":1},
    {"url": "https://data.worldbank.org",           "domain":"navigation","goal":"extract featured dataset names and categories",  "action_type":"extract","difficulty":1},
    {"url": "https://ourworldindata.org",           "domain":"navigation","goal":"extract chart and article topic names",          "action_type":"extract","difficulty":1},
    {"url": "https://www.census.gov/data",          "domain":"navigation","goal":"extract dataset category names",                "action_type":"extract","difficulty":1},
    {"url": "https://data.un.org",                  "domain":"navigation","goal":"extract database names and categories",          "action_type":"extract","difficulty":1},
    {"url": "https://ec.europa.eu/eurostat",        "domain":"navigation","goal":"extract statistical theme names",               "action_type":"extract","difficulty":1},
    {"url": "https://www.imf.org/en/Data",          "domain":"navigation","goal":"extract data publication names",                "action_type":"extract","difficulty":1},
    {"url": "https://www.wto.org/english/res_e",    "domain":"navigation","goal":"extract research publication titles",            "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  HEALTH / MEDICAL (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.webmd.com",                "domain":"extract","goal":"extract featured health article titles",            "action_type":"extract","difficulty":1},
    {"url": "https://www.healthline.com",           "domain":"extract","goal":"extract article titles from the front page",        "action_type":"extract","difficulty":1},
    {"url": "https://medlineplus.gov",              "domain":"extract","goal":"extract health topic names from A-Z list",          "action_type":"extract","difficulty":1},
    {"url": "https://www.mayoclinic.org/diseases-conditions","domain":"extract","goal":"extract disease and condition names",      "action_type":"extract","difficulty":1},
    {"url": "https://www.nih.gov",                  "domain":"extract","goal":"extract research news titles",                     "action_type":"extract","difficulty":1},
    {"url": "https://www.cdc.gov/diseasesconditions","domain":"extract","goal":"extract disease names from the directory",         "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  TRAVEL (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.booking.com",              "domain":"forms",  "goal":"search for hotels in Paris and extract top results","action_type":"type",   "difficulty":2},
    {"url": "https://www.airbnb.com",               "domain":"forms",  "goal":"search for apartments in London",                  "action_type":"type",   "difficulty":2},
    {"url": "https://www.expedia.com",              "domain":"forms",  "goal":"search for flights from New York to London",        "action_type":"type",   "difficulty":2},
    {"url": "https://www.tripadvisor.com",          "domain":"forms",  "goal":"search for restaurants in Rome and extract names",  "action_type":"type",   "difficulty":2},
    {"url": "https://www.skyscanner.com",           "domain":"forms",  "goal":"search for cheapest flight to Tokyo",               "action_type":"type",   "difficulty":2},
    {"url": "https://www.kayak.com",                "domain":"forms",  "goal":"search for hotels in Dubai this weekend",           "action_type":"type",   "difficulty":2},
    {"url": "https://www.lonelyplanet.com",         "domain":"extract","goal":"extract featured destination names",               "action_type":"extract","difficulty":1},
    {"url": "https://www.timeout.com",              "domain":"extract","goal":"extract city names and featured articles",          "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  DESIGN / CREATIVE (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://dribbble.com",                 "domain":"extract","goal":"extract featured design shot titles and designers",  "action_type":"extract","difficulty":1},
    {"url": "https://www.behance.net",              "domain":"extract","goal":"extract featured project names and categories",      "action_type":"extract","difficulty":1},
    {"url": "https://www.awwwards.com",             "domain":"extract","goal":"extract nominated website names and categories",     "action_type":"extract","difficulty":2},
    {"url": "https://www.designspiration.com",      "domain":"extract","goal":"scroll and extract visible design category names",   "action_type":"scroll", "difficulty":2},
    {"url": "https://www.canva.com/templates",      "domain":"extract","goal":"extract featured template category names",           "action_type":"extract","difficulty":1},
    {"url": "https://www.adobe.com/products",       "domain":"extract","goal":"extract all Adobe product names",                  "action_type":"extract","difficulty":1},
    {"url": "https://fonts.google.com",             "domain":"extract","goal":"extract top 10 font names and categories",           "action_type":"extract","difficulty":1},
    {"url": "https://www.fontsquirrel.com",         "domain":"extract","goal":"extract all font names from the page",              "action_type":"extract","difficulty":1},
    {"url": "https://coolors.co/palettes/trending",  "domain":"extract","goal":"extract trending color palette names",              "action_type":"extract","difficulty":1},
    {"url": "https://color.adobe.com/explore",      "domain":"extract","goal":"extract featured color theme names",                "action_type":"extract","difficulty":1},
    {"url": "https://www.flaticon.com",             "domain":"forms",  "goal":"search for arrow icons and extract top results",    "action_type":"type",   "difficulty":1},
    {"url": "https://unsplash.com",                 "domain":"forms",  "goal":"search for mountain landscape photos",              "action_type":"type",   "difficulty":1},
    {"url": "https://www.pexels.com",               "domain":"forms",  "goal":"search for city skyline photos",                    "action_type":"type",   "difficulty":1},
    {"url": "https://pixabay.com",                  "domain":"forms",  "goal":"search for nature background images",               "action_type":"type",   "difficulty":1},
    {"url": "https://icons8.com/icons",             "domain":"forms",  "goal":"search for home icon and extract top results",      "action_type":"type",   "difficulty":1},
    {"url": "https://www.svgrepo.com",              "domain":"forms",  "goal":"search for user icon and extract svg names",        "action_type":"type",   "difficulty":1},

    # ──────────────────────────────────────────────
    #  GAMING (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://store.steampowered.com",       "domain":"extract","goal":"extract featured and top seller game names",        "action_type":"extract","difficulty":1},
    {"url": "https://store.steampowered.com/charts","domain":"extract","goal":"extract top played game names and player counts",   "action_type":"extract","difficulty":1},
    {"url": "https://www.igdb.com/games",           "domain":"extract","goal":"extract game names and ratings",                   "action_type":"extract","difficulty":1},
    {"url": "https://www.metacritic.com/game",      "domain":"extract","goal":"extract top rated game names and scores",           "action_type":"extract","difficulty":1},
    {"url": "https://www.gog.com/games",            "domain":"extract","goal":"extract game names and prices",                    "action_type":"extract","difficulty":1},
    {"url": "https://itch.io",                      "domain":"extract","goal":"extract featured indie game names",                "action_type":"extract","difficulty":1},
    {"url": "https://www.epicgames.com/store/en-US","domain":"extract","goal":"extract featured free game names",                 "action_type":"extract","difficulty":1},
    {"url": "https://playvalorant.com/en-us/agents","domain":"extract","goal":"extract all agent names and roles",                "action_type":"extract","difficulty":1},
    {"url": "https://www.leagueoflegends.com/en-us/champions","domain":"extract","goal":"extract champion names and roles",       "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  WIKIPEDIA / REFERENCE (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://en.wikipedia.org/wiki/Main_Page","domain":"extract","goal":"extract featured article title and section names","action_type":"extract","difficulty":1},
    {"url": "https://en.wikipedia.org/wiki/Artificial_intelligence","domain":"extract","goal":"extract all section headings from the article","action_type":"extract","difficulty":1},
    {"url": "https://en.wikipedia.org/wiki/Python_(programming_language)","domain":"extract","goal":"extract article headings and key facts","action_type":"extract","difficulty":1},
    {"url": "https://en.wikipedia.org/wiki/Machine_learning","domain":"extract","goal":"extract all h2 section names from article","action_type":"extract","difficulty":1},
    {"url": "https://en.wiktionary.org/wiki/Main_Page","domain":"extract","goal":"extract featured word and its definitions",      "action_type":"extract","difficulty":1},
    {"url": "https://www.britannica.com",           "domain":"extract","goal":"extract featured article titles",                  "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  ARABIC WEBSITES (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.aljazeera.net",            "domain":"extract","goal":"استخراج عناوين الأخبار الرئيسية من الصفحة",        "action_type":"extract","difficulty":1},
    {"url": "https://arabic.cnn.com",              "domain":"extract","goal":"استخراج عناوين المقالات البارزة",                   "action_type":"extract","difficulty":1},
    {"url": "https://www.skynewsarabia.com",        "domain":"extract","goal":"استخراج عناوين الأخبار من الصفحة الرئيسية",        "action_type":"extract","difficulty":1},
    {"url": "https://www.bbc.com/arabic",           "domain":"extract","goal":"استخراج عناوين الأخبار العربية",                   "action_type":"extract","difficulty":1},
    {"url": "https://www.alarabiya.net",            "domain":"extract","goal":"استخراج أبرز عناوين الأخبار",                     "action_type":"extract","difficulty":1},
    {"url": "https://www.youm7.com",                "domain":"extract","goal":"استخراج عناوين أبرز الأخبار المصرية",              "action_type":"extract","difficulty":1},
    {"url": "https://www.masrawy.com",              "domain":"extract","goal":"استخراج عناوين الأخبار والمقالات",                 "action_type":"extract","difficulty":1},
    {"url": "https://www.elwatannews.com",          "domain":"extract","goal":"استخراج عناوين الأخبار من الصفحة",                "action_type":"extract","difficulty":1},
    {"url": "https://www.amwaj.media",              "domain":"extract","goal":"extract article titles from the front page",        "action_type":"extract","difficulty":1},
    {"url": "https://ar.wikipedia.org/wiki",        "domain":"extract","goal":"استخراج عنوان المقالة المميزة",                    "action_type":"extract","difficulty":1},
    {"url": "https://www.bayt.com",                 "domain":"extract","goal":"استخراج عناوين الوظائف والشركات",                  "action_type":"extract","difficulty":1},
    {"url": "https://wuzzuf.net/jobs/egypt",        "domain":"extract","goal":"استخراج عناوين الوظائف المتاحة في مصر",            "action_type":"extract","difficulty":2},
    {"url": "https://www.noon.com/egypt-ar",        "domain":"extract","goal":"استخراج أسماء المنتجات المميزة والأسعار",          "action_type":"extract","difficulty":1},
    {"url": "https://souq.com",                     "domain":"extract","goal":"استخراج أسماء المنتجات الرائجة",                  "action_type":"extract","difficulty":1},

    # ──────────────────────────────────────────────
    #  MISCELLANEOUS HIGH-TRAFFIC (domain: extract)
    # ──────────────────────────────────────────────
    {"url": "https://www.imdb.com/chart/top",       "domain":"extract","goal":"extract top 10 movie titles and ratings",           "action_type":"extract","difficulty":1},
    {"url": "https://www.imdb.com/chart/moviemeter","domain":"extract","goal":"extract trending movie titles",                    "action_type":"extract","difficulty":1},
    {"url": "https://letterboxd.com/films/popular", "domain":"extract","goal":"extract popular film names and years",             "action_type":"extract","difficulty":1},
    {"url": "https://www.rottentomatoes.com",       "domain":"extract","goal":"extract featured movie titles and scores",          "action_type":"extract","difficulty":1},
    {"url": "https://www.goodreads.com/list/show/1","domain":"extract","goal":"extract book titles and author names from list",   "action_type":"extract","difficulty":1},
    {"url": "https://www.goodreads.com/shelf/show/to-read","domain":"extract","goal":"extract most shelved book titles",          "action_type":"extract","difficulty":1},
    {"url": "https://openlibrary.org/trending",     "domain":"extract","goal":"extract trending book titles and authors",          "action_type":"extract","difficulty":1},
    {"url": "https://www.last.fm/charts",           "domain":"extract","goal":"extract top artist and track names",               "action_type":"extract","difficulty":1},
    {"url": "https://www.allmusic.com",             "domain":"extract","goal":"extract featured album and artist names",           "action_type":"extract","difficulty":1},
    {"url": "https://pitchfork.com",                "domain":"extract","goal":"extract album review titles and scores",            "action_type":"extract","difficulty":1},
    {"url": "https://bandcamp.com",                 "domain":"extract","goal":"extract featured artist and album names",           "action_type":"extract","difficulty":1},
    {"url": "https://soundcloud.com/charts/top",    "domain":"extract","goal":"extract top track names and artists",              "action_type":"extract","difficulty":1},
    {"url": "https://www.merriam-webster.com",      "domain":"forms",  "goal":"search for definition of algorithm",               "action_type":"type",   "difficulty":1},
    {"url": "https://dictionary.cambridge.org",     "domain":"forms",  "goal":"search for definition of intelligence",             "action_type":"type",   "difficulty":1},
    {"url": "https://thesaurus.com",                "domain":"forms",  "goal":"search for synonyms of beautiful",                 "action_type":"type",   "difficulty":1},
    {"url": "https://www.etymonline.com",           "domain":"forms",  "goal":"search for etymology of computer",                 "action_type":"type",   "difficulty":1},
    {"url": "https://www.timeanddate.com",          "domain":"extract","goal":"extract current time zones and world clock data",   "action_type":"extract","difficulty":1},
    {"url": "https://www.worldometers.info",        "domain":"extract","goal":"extract world population and key statistics",       "action_type":"extract","difficulty":1},
    {"url": "https://www.numbeo.com/cost-of-living","domain":"extract","goal":"extract city names and cost of living indices",     "action_type":"extract","difficulty":1},
    {"url": "https://www.xe.com",                   "domain":"forms",  "goal":"search for USD to EUR exchange rate",               "action_type":"type",   "difficulty":1},
    {"url": "https://www.investing.com/currencies", "domain":"extract","goal":"extract currency pair names and exchange rates",    "action_type":"extract","difficulty":1},
    {"url": "https://weather.com",                  "domain":"forms",  "goal":"search for weather in Cairo Egypt",                 "action_type":"type",   "difficulty":1},
    {"url": "https://openweathermap.org",           "domain":"forms",  "goal":"search for weather in London",                     "action_type":"type",   "difficulty":1},
    {"url": "https://www.flightradar24.com",        "domain":"extract","goal":"extract number of flights currently in air",        "action_type":"extract","difficulty":2},
    {"url": "https://www.marinetraffic.com",        "domain":"extract","goal":"navigate to main map page",                        "action_type":"navigate","difficulty":2},
    {"url": "https://planetarycomputer.microsoft.com","domain":"navigation","goal":"navigate to catalog and extract dataset names","action_type":"navigate","difficulty":2},

]


# ──────────────────────────────────────────────────────────────
#  Helper functions
# ──────────────────────────────────────────────────────────────

def get_tasks_for_domain(domain: str) -> List[tuple]:
    """Returns list of (goal, url) for a specific domain."""
    return [
        (t["goal"], t["url"])
        for t in ALL_WEBSITE_TASKS
        if t["domain"] == domain
    ]


def get_tasks_by_difficulty(difficulty: int) -> List[tuple]:
    """Returns (goal, url) for tasks of a specific difficulty level."""
    return [
        (t["goal"], t["url"])
        for t in ALL_WEBSITE_TASKS
        if t["difficulty"] == difficulty
    ]


def get_all_as_tuples() -> List[tuple]:
    """Returns all tasks as (goal, url) tuples for drop-in with collect_and_train."""
    return [(t["goal"], t["url"]) for t in ALL_WEBSITE_TASKS]


def get_domain_stats() -> dict:
    """Returns count per domain."""
    from collections import Counter
    return dict(Counter(t["domain"] for t in ALL_WEBSITE_TASKS))


def get_difficulty_stats() -> dict:
    """Returns count per difficulty."""
    from collections import Counter
    return dict(Counter(t["difficulty"] for t in ALL_WEBSITE_TASKS))


if __name__ == "__main__":
    print(f"Total websites : {len(ALL_WEBSITE_TASKS)}")
    print(f"Domain stats   : {get_domain_stats()}")
    print(f"Difficulty     : {get_difficulty_stats()}")
