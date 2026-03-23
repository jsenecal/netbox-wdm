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

SECRET_KEY = "r(m)9nLGnz$(_q3-4sdr-yJF99I-P3Ba_7TKKE0d[&Z5Q"
