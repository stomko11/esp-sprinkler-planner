"""Constants for ESP Sprinkler Planner."""
DOMAIN = "esp_sprinkler_planner"
EVENT = f"{DOMAIN}_event"
STORAGE_VERSION = 1

CONF_DEVICE = "device_id"
CONF_CONTROLLER = "controller"
CONF_VALVES = "valves"
CONF_VALVE_OVERLAP = "valve_overlap"

CONTROLLER_KEYS = ("main_switch", "reverse", "standby", "multiplier", "repeat")

OPT_RESTORE = "restore"
OPT_IMPORT = "import_config"      # settings from a backup file, moved into the store at first start
OPT_IMPORT_NOTES = "import_notes"
OPT_WATCHDOG = "watchdog_margin"

DEFAULT_WATCHDOG = 10  # minutes past the planned end before the run is stopped
PLAN_DAYS = 8          # days planned ahead for scheduling (the next run can be days away when runs are skipped)
