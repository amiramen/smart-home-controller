import time
from abc import ABC, abstractmethod
import datetime
from enum import Enum, auto

import attr
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request, redirect, url_for
from typing import List, Dict, Type, Callable

# from flask_crontab import Crontab
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import ClauseElement

app = Flask(__name__)
# crontab = Crontab(app)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.sqlite"  # "mysql://root:toor@localhost/to_do_list"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class SmartHome(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    home_name = db.Column(db.String(45))
    switches = db.relationship('SmartSwitch', backref='smart_home')


class SmartSwitch(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip = db.Column(db.String(45))
    switch_id = db.Column(db.String(45))
    switch_name = db.Column(db.String(45), default="New switch")
    switch_type = db.Column(db.String(45))
    open_position = db.Column(db.Integer, default=10)
    stop_open_position = db.Column(db.Integer, default=100)
    close_position = db.Column(db.Integer, default=120)
    stop_close_position = db.Column(db.Integer, default=20)
    standby_position = db.Column(db.Integer, default=60)
    smart_home_id = db.Column(db.Integer, db.ForeignKey('smart_home.id'))

    def move(self, target_position):
        requests.get(f"http://{self.ip}/servo/{target_position}")

    @staticmethod
    def wait(seconds):
        time.sleep(float(seconds))

    def open(self, duration):
        self.move(self.open_position)
        self.wait(duration)
        self.move(self.stop_open_position)
        self.wait(0.1)
        self.move(self.standby_position)

    def close(self, duration):
        self.move(self.close_position)
        print(duration)
        self.wait(duration)
        self.move(self.stop_close_position)
        self.wait(0.1)
        self.move(self.standby_position)

    def test_position(self, position, duration):
        self.move(position)
        self.wait(duration)
        self.move(self.standby_position)


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


SWITCH_TO_CLASS_MAP: Dict[str, Type[SmartSwitch]] = {"curtain_switch": SmartSwitch}


# @crontab.job()
def look_for_job_to_run_now():
    now = datetime.datetime.now()
    for command in smart_home.repetitive_commands:
        if command.should_run(now):
            command.run()


def get_or_create(session, model, filter_by_field, defaults=None, **kwargs):
    instance = session.query(model).filter_by(**{filter_by_field: kwargs[filter_by_field]}).first()
    if instance:
        return instance, False
    else:
        params = {k: v for k, v in kwargs.items() if not isinstance(v, ClauseElement)}
        params.update(defaults or {})
        instance = model(**params)
        session.add(instance)
        return instance, True

@app.route("/update_settings", methods=["POST"])
def update_settings():
    switch = db.session.query(SmartSwitch).filter_by(id=request.form.get("id")).first()
    if switch:
        switch.switch_name = request.form.get("switch_name")
        switch.open_position = request.form.get("open_position")
        switch.stop_open_position = request.form.get("stop_open_position")
        switch.close_position = request.form.get("close_position")
        switch.stop_close_position = request.form.get("stop_close_position")
        switch.standby_position = request.form.get("standby_position")
        db.session.commit()
        return redirect(url_for('settings_page'))
    else:
        return f"Error! Switch not found {id}"


@app.route("/delete/<int:id>")
def delete_switch(id):
    switch = db.session.query(SmartSwitch).filter_by(id=id).first()
    if switch:
        db.session.delete(switch)
        db.session.commit()
        return redirect(url_for('settings_page'))
    else:
        return f"Error! Switch not found {id}"


@app.route("/")
def settings_page():
    return render_template("settings.html", switches=SmartSwitch.query.all())


@app.route("/notify_switch_wakeup/<switch_id>/<switch_type>/<ip>")
def notify_switch_wakeup(switch_id: str, switch_type: str, ip: str):
    if switch_type in SWITCH_TO_CLASS_MAP:
        switch, is_added = get_or_create(db.session, SmartSwitch, "switch_id", None,
                                         ip=ip, switch_id=switch_id, switch_type=switch_type)
        if is_added:
            return_value = "New switch added!"
        else:
            switch.ip = ip
            return_value = "IP updated!"
        db.session.commit()
    else:
        return_value = f"Error - switch type not familiar: {switch_type}"

    return return_value


@app.route("/open_curtain/<int:id>/<duration>")
def open_curtain(id, duration):
    switch = db.session.query(SmartSwitch).filter_by(id=id).first()
    if switch:
        switch.open(duration)
        return "success"
    return "failed: switch doesn't exists"


@app.route("/close_curtain/<int:id>/<duration>")
def close_curtain(id, duration):
    switch = db.session.query(SmartSwitch).filter_by(id=id).first()
    if switch:
        switch.close(duration)
        return "success"
    return "failed: switch doesn't exists"


@app.route("/test_position/<int:id>/<position>")
def test_position(id, position):
    switch = db.session.query(SmartSwitch).filter_by(id=id).first()
    if switch:
        switch.test_position(position, 2)
        return "success"
    return "failed: switch doesn't exists"

if __name__ == "__main__":
    # crontab.init_app(app)
    smart_home = {}
    app.run(host="0.0.0.0", port=8090, debug=True)
