import json
import os
import re
from datetime import datetime

DEFAULT_DATA = {
    "rules": ["Study every day", "Exercise for health", "Sleep on time", "Avoid unnecessary phone usage"],
    "timetable": {
        "09:00": "College starts",
        "16:20": "College ends",
        "18:00": "Study / Skill Growth",
        "20:00": "Dinner",
        "21:00": "Revision",
        "22:30": "Sleep preparation",
    },
    "tasks": [],
}

class JarvisCore:
    def __init__(self, path):
        self.path = path
        self.data = self.load_data()

    def load_data(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in DEFAULT_DATA.items():
                    data.setdefault(k, v.copy() if isinstance(v, dict) else list(v))
                return data
        except Exception:
            pass
        data = json.loads(json.dumps(DEFAULT_DATA))
        self._save(data)
        return data

    def _save(self, data=None):
        if data is not None:
            self.data = data
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    @staticmethod
    def norm(s):
        s = str(s).lower().strip()
        s = s.replace("what's", "what is").replace("today's", "today")
        s = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def number(s):
        m = re.search(r"\b(\d+)\b", s)
        return int(m.group(1)) if m else None

    def handle(self, raw):
        cmd = self.norm(raw)
        if not cmd:
            return "I did not hear a command, Boss."

        if cmd in {"hi", "hello", "hey", "hii", "good morning", "good afternoon", "good evening"}:
            return "Hello Boss. I am ready."
        if cmd in {"help", "commands", "what can you do", "what can you do for me"}:
            return self.help_text()
        if cmd in {"who are you", "what are you", "introduce yourself"}:
            return "I am VYRo, your personal voice assistant."
        if cmd in {"how are you", "how are you vyro"}:
            return "I am online and ready, Boss."
        if cmd in {"thank you", "thanks", "thank you vyro", "thanks vyro"}:
            return "You're welcome, Boss."
        if cmd in {"time", "what time is it", "what is the time", "current time", "tell me the time", "show time", "samay kya hai", "time batao"} or "time bata" in cmd:
            return "Current time is " + datetime.now().strftime("%I:%M %p")
        if cmd in {"date", "what is the date", "what date is it", "today date", "today date kya hai", "today ki date kya hai", "aaj ki date kya hai", "current date", "tell me the date", "show date"} or "date kya" in cmd or "tarikh" in cmd:
            return "Today is " + datetime.now().strftime("%A, %d %B %Y")
        if cmd in {"rules", "rule", "show rules", "show my rules", "my rules", "daily rules", "mere rules", "mere rules dikhao", "rules dikhao"}:
            return self.show_rules()
        if cmd in {"timetable", "schedule", "show timetable", "show my timetable", "my timetable", "daily schedule", "mera timetable", "timetable dikhao", "schedule dikhao"}:
            return self.show_timetable()
        if cmd in {"tasks", "task", "show tasks", "show my tasks", "my tasks", "pending tasks", "todo", "to do", "mere tasks", "mere task dikhao", "tasks dikhao"}:
            return self.show_tasks()
        if cmd in {"summary", "daily summary", "my summary", "today summary", "status", "daily report"}:
            return self.show_summary()

        if cmd in {"clear completed", "clear completed tasks", "remove completed tasks", "completed tasks clear karo"}:
            return self.clear_completed_tasks()

        m = re.match(r"(?:add|create|new|remember)\s+(?:a\s+)?task\s+(.+)$", cmd)
        if not m:
            m = re.match(r"(?:task|kaam)\s+(?:add|banao)\s+(.+)$", cmd)
        if not m:
            m = re.match(r"(?:ek\s+)?task\s+add\s+karo\s+(.+)$", cmd)
        if m:
            return self.add_task(m.group(1).strip())

        if any(x in cmd for x in ["complete", "finish", "mark done", "done karo", "complete karo"]):
            n = self.number(cmd)
            if n is not None:
                return self.complete_task(n)
        if cmd.startswith(("delete", "remove")) or "delete task" in cmd or "task delete" in cmd:
            n = self.number(cmd)
            if n is not None:
                return self.delete_task(n)

        m = re.match(r"(?:add|create|new|remember)\s+(?:a\s+)?rule\s+(.+)$", cmd)
        if not m:
            m = re.match(r"rule\s+add\s+karo\s+(.+)$", cmd)
        if m:
            return self.add_rule(m.group(1).strip())
        if cmd.startswith(("delete rule", "remove rule", "rule delete")):
            n = self.number(cmd)
            if n is not None:
                return self.delete_rule(n)

        m = re.match(r"(?:set|add|change)\s+(?:timetable|schedule)\s+(\d{1,2}:\d{2})\s+(.+)$", cmd)
        if m:
            return self.set_timetable(m.group(1), m.group(2).strip())

        return "Sorry Boss, I don't know that command yet. Say help to hear the commands I can do."

    def add_task(self, task):
        self.data["tasks"].append({"task": task, "completed": False, "created": datetime.now().isoformat(timespec="seconds")})
        self._save()
        return "Task added: " + task

    def complete_task(self, n):
        i = n - 1
        if not 0 <= i < len(self.data["tasks"]):
            return f"Task {n} does not exist."
        self.data["tasks"][i]["completed"] = True
        self._save()
        return "Task completed: " + self.data["tasks"][i]["task"]

    def delete_task(self, n):
        i = n - 1
        if not 0 <= i < len(self.data["tasks"]):
            return f"Task {n} does not exist."
        removed = self.data["tasks"].pop(i)
        self._save()
        return "Task deleted: " + removed["task"]

    def clear_completed_tasks(self):
        before = len(self.data["tasks"])
        self.data["tasks"] = [x for x in self.data["tasks"] if not x.get("completed")]
        self._save()
        return f"Removed {before - len(self.data['tasks'])} completed task(s)."

    def add_rule(self, rule):
        self.data["rules"].append(rule)
        self._save()
        return "Rule added: " + rule

    def delete_rule(self, n):
        i = n - 1
        if not 0 <= i < len(self.data["rules"]):
            return f"Rule {n} does not exist."
        removed = self.data["rules"].pop(i)
        self._save()
        return "Rule deleted: " + removed

    def set_timetable(self, t, activity):
        h, m = t.split(":")
        t = f"{int(h):02d}:{int(m):02d}"
        self.data["timetable"][t] = activity
        self._save()
        return f"Timetable updated: {t} is {activity}."

    def show_rules(self):
        if not self.data["rules"]:
            return "You have no rules saved."
        return "Your daily rules are: " + "; ".join(f"number {i}, {x}" for i, x in enumerate(self.data["rules"], 1))

    def show_timetable(self):
        return "Your timetable is: " + "; ".join(f"{t}, {a}" for t, a in sorted(self.data["timetable"].items()))

    def show_tasks(self):
        if not self.data["tasks"]:
            return "You have no tasks yet."
        return "Your tasks are: " + "; ".join(f"number {i}, {'completed' if x.get('completed') else 'pending'}, {x['task']}" for i, x in enumerate(self.data["tasks"], 1))

    def show_summary(self):
        done = sum(1 for x in self.data["tasks"] if x.get("completed"))
        pending = len(self.data["tasks"]) - done
        return (f"Daily summary. Date {datetime.now().strftime('%A, %d %B %Y')}. "
                f"Time {datetime.now().strftime('%I:%M %p')}. "
                f"Rules {len(self.data['rules'])}. Completed tasks {done}. Pending tasks {pending}. "
                f"Timetable entries {len(self.data['timetable'])}.")

    @staticmethod
    def help_text():
        return ("I can tell time and date; show rules, timetable, tasks and daily summary; "
                "add, complete and delete tasks; add and delete rules; change timetable entries; "
                "and answer basic questions. Try: add task finish Python project, complete task 1, or show my tasks.")
