####
## This file serves as the base configuration for NetBox.
## Settings may be overridden in configuration.d/ files.
####

ALLOWED_HOSTS = ["*"]

DATABASE = {
    "NAME": "netbox",
    "USER": "netbox",
    "PASSWORD": "netbox",
    "HOST": "postgres",
    "PORT": "",
    "CONN_MAX_AGE": 300,
    "ENGINE": "django.contrib.gis.db.backends.postgis",
}

REDIS = {
    "tasks": {
        "HOST": "redis",
        "PORT": 6379,
        "PASSWORD": "netbox_redis_pass",
        "DATABASE": 0,
        "SSL": False,
    },
    "caching": {
        "HOST": "redis",
        "PORT": 6379,
        "PASSWORD": "netbox_redis_pass",
        "DATABASE": 1,
        "SSL": False,
    },
}

SECRET_KEY = "IN1nA18P6zgAWu6QaZcfoujJoHt7u6h_55WJssbf2J2mPfrJGmogaiqmmGlXjh03mZXYHomFgpZuYZwvDHC74w"

DEBUG = True

DEVELOPER = True

API_TOKEN_PEPPERS = {1: "test-pepper-for-development-only-not-for-production"}
