import time
from abc import ABC, abstractmethod
import datetime
from enum import Enum, auto

import attr
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request
from typing import List, Dict, Type, Callable

from flask_crontab import Crontab
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
crontab = Crontab(app)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.sqlite"  # "mysql://root:toor@localhost/to_do_list"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

@attr.s
class SwitchConfig:
    id: str = attr.ib()
    ip: str = attr.ib()
    switch_name: str = attr.ib(default="New switch")
    open_position: int = attr.ib(default=10)
    stop_open_position: int = attr.ib(default=100)
    close_position: int = attr.ib(default=120)
    stop_close_position: int = attr.ib(default=20)
    standby_position: int = attr.ib(default=60)


class Task(ABC):

    @abstractmethod
    def do(self, switch_config: SwitchConfig):
        pass


@attr.s
class Wait(Task):
    time = attr.ib(default=0)

    def do(self, switch_config: SwitchConfig):
        time.sleep(self.time)


@attr.s
class Move(Task):
    target_position = attr.ib(default=60)

    def do(self, switch_config: SwitchConfig):
        requests.get(f"http://{switch_config.ip}/servo/{self.target_position}")


@attr.s
class Action:
    tasks: List[Task] = attr.ib()

    def run(self, switch_config: SwitchConfig):
        for task in self.tasks:
            task.do(switch_config)


@attr.s
class SmartSwitch:
    switch_config: SwitchConfig = attr.ib()
    commands_map: Dict[str, Callable] = {}

    def run(self, command, *kargs,**kwargs):
        if command in self.commands_map:
            self.commands_map[command](*kargs, **kwargs)
        else:
            print(f"Error! command '{command}' not found. Existing commands:{self.commands_map.keys()}")

    @classmethod
    def from_notify_switch_wakeup(cls, id: str, ip: str):
        return cls(switch_config=SwitchConfig(id, ip))


@attr.s
class SmartCurtainSwitch(SmartSwitch):

    def __attrs_post_init__(self):
        commands_map = {"open": self.open,
                        "close": self.close}

    def open(self, duration: int):
        Action([Move(self.switch_config.open_position),
                Wait(duration),
                Move(self.switch_config.stop_open_position),
                Wait(0.1),
                Move(self.switch_config.standby_position)]
               ).run(self.switch_config)

    def close(self, duration: int):
        Action([Move(self.switch_config.close_position),
                Wait(duration),
                Move(self.switch_config.stop_close_position),
                Wait(0.1),
                Move(self.switch_config.standby_position)]
               ).run(self.switch_config)


@attr.s
class RepetitiveCommand:
    switch: SmartSwitch
    command_name: str
    duration: int
    hour: int
    minute: int
    days: List[int]

    def should_run(self, now: datetime.datetime):
        return now.weekday() in self.days and now.hour == self.hour and now.minute == self.minute

    def run(self):
        self.switch.run(self.command_name, self.duration)


class SmartHome(db.Model):
    switches: Dict[int, SmartSwitch] = attr.ib(default=[])
    repetitive_commands: List[RepetitiveCommand] = []



SWITCH_TO_CLASS_MAP: Dict[str, Type[SmartSwitch]] = {"curtain_switch": SmartCurtainSwitch}


@app.route("/")
def settings_page():
    print(smart_home.switches)
    return render_template("settings.html", switches=smart_home.switches)


@app.route("/update_settings", methods=["POST"])
def update_settings():
    id = request.form.get("id")
    if id in smart_home.switches:
        smart_home.switches[id].switch_name = request.form.get("switch_name")
        smart_home.switches[id].open_position = request.form.get("open_position")
        smart_home.switches[id].stop_open_position = request.form.get("stop_open_position")
        smart_home.switches[id].close_position = request.form.get("close_position")
        smart_home.switches[id].stop_close_position = request.form.get("stop_close_position")
        smart_home.switches[id].standby_position = request.form.get("standby_position")


@app.route("/notify_switch_wakeup/<switch_id>/<switch_type>/<ip>")
def notify_switch_wakeup(switch_id: str, switch_type: str, ip: str):
    if switch_id in smart_home.switches:
        smart_home.switches[switch_id].ip = ip
        return "IP updated!"
    elif switch_type in SWITCH_TO_CLASS_MAP:
        smart_home.switches[switch_id] = SWITCH_TO_CLASS_MAP[switch_type].from_notify_switch_wakeup(ip=ip, id=switch_id)
        return "New switch added!"
    return f"Error - switch type not familiar: {switch_type}"


@app.route("/open_curtain/<switch_id>/<duration>")
def open_curtain(switch_id, duration):
    if switch_id in smart_home.switches and isinstance(smart_home.switches[switch_id], SmartCurtainSwitch):
        smart_home.switches[switch_id].open(int(duration))
        return "success"
    return "failed: switch doesn't exists"


@app.route("/close_curtain/<switch_id>/<duration>")
def close_curtain(switch_id, duration):
    if switch_id in smart_home.switches and isinstance(smart_home.switches[switch_id], SmartCurtainSwitch):
        smart_home.switches[switch_id].close(int(duration))
        return "success"
    return "failed: switch doesn't exists"


@crontab.job()
def look_for_job_to_run_now():
    now = datetime.datetime.now()
    for command in smart_home.repetitive_commands:
        if command.should_run(now):
            command.run()


if __name__ == "__main__":
    switches = {}
    smart_home = SmartHome(switches=switches)
    crontab.init_app(app)
    app.run(host="0.0.0.0", port=8090, debug=True)
