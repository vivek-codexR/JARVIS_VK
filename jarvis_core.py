import json
import os
import re
from copy import deepcopy
from datetime import datetime

DEFAULT_DATA = {
    "rules": [
        "Study every day",
        "Exercise for health",
        "Sleep on time",
        "Avoid unnecessary phone usage"
    ],
    "tasks": [],
    "timetable": {
        "09:00": "College starts",
        "16:20": "College ends",
        "18:00": "Study / Skill Growth",
        "20:00": "Dinner",
        "21:00": "Revision",
        "22:30": "Sleep preparation"
    }
}


class JarvisCore:
    def __init__(self, data_file):
        self.data_file = data_file
        self.data = self.load_data()

    def load_data(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("rules", deepcopy(DEFAULT_DATA["rules"]))
                    data.setdefault("tasks", [])
                    data.setdefault("timetable", deepcopy(DEFAULT_DATA["timetable"]))
                    return data
        except Exception:
            pass
        data = deepcopy(DEFAULT_DATA)
        self.save_data(data)
        return data

    def save_data(self, data=None):
        data = data or self.data
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def handle(self, raw):
        cmd = re.sub(r"\s+", " ", raw.strip().lower()).strip()
        if not cmd:
            return "I am listening."

        if cmd in {"hi", "hello", "hey", "hii", "hlo", "good morning",
                   "good afternoon", "good evening", "namaste", "नमस्ते"}:
            return "Hello Boss. I am ready to help."

        if cmd in {"help", "commands", "what can you do", "क्या कर सकते हो",
                   "क्या कर सकते हो jarvis"}:
            return self.help_text()

        if cmd in {"time", "what time is it", "what is the time",
                   "current time", "tell me the time", "show time",
                   "समय क्या है", "टाइम क्या है", "अभी कितने बजे हैं",
                   "अभी टाइम क्या है"}:
            return "Current time: " + datetime.now().strftime("%I:%M %p")

        if cmd in {"date", "what is the date", "what date is it",
                   "today date", "today's date", "current date",
                   "tell me the date", "show date",
                   "आज की तारीख", "आज की तारीख क्या है", "आज कौन सी तारीख है"}:
            return "Today: " + datetime.now().strftime("%A, %d %B %Y")

        if cmd in {"rules", "rule", "show rules", "show my rules",
                   "my rules", "daily rules", "मेरे रूल्स दिखाओ",
                   "मेरे नियम दिखाओ", "रूल्स दिखाओ"}:
            return self.show_rules()

        if cmd in {"timetable", "schedule", "show timetable",
                   "show my timetable", "my timetable", "daily schedule",
                   "मेरा टाइमटेबल दिखाओ", "टाइमटेबल दिखाओ",
                   "आज का टाइमटेबल दिखाओ"}:
            return self.show_timetable()

        if cmd in {"tasks", "task", "show tasks", "show my tasks",
                   "my tasks", "pending tasks", "todo", "to do",
                   "मेरे टास्क दिखाओ", "टास्क दिखाओ", "पेंडिंग टास्क दिखाओ"}:
            return self.show_tasks()

        if cmd in {"summary", "daily summary", "my summary",
                   "today summary", "status", "मेरा समरी दिखाओ",
                   "आज का समरी दिखाओ", "समरी दिखाओ"}:
            return self.show_summary()

        task = self.extract_after_prefix(cmd, [
            "add task ", "add a task ", "create task ",
            "create a task ", "new task ", "remember task ",
            "task add ", "टास्क जोड़ो ", "टास्क जोड़ना है ",
            "टास्क ऐड करो ", "टास्क ऐड कर दो "
        ])
        if task:
            return self.add_task(task)

        # Common Hinglish forms where speech recognition inserts extra words.
        m = re.match(r"(?:add|create|new)\s+(?:a\s+)?task\s*(?:to\s*)?(.+)$", cmd)
        if m:
            return self.add_task(m.group(1).strip())

        number = self.extract_number(cmd, ["complete", "finish", "done", "mark"])
        if number is not None:
            return self.complete_task(number)

        m = re.search(r"(?:complete|finish|done|mark)\s+(?:task\s+)?(\d+)", cmd)
        if m:
            return self.complete_task(int(m.group(1)))

        number = self.extract_number(cmd, ["delete", "remove"])
        if number is not None and ("task" in cmd or cmd.startswith(("delete ", "remove "))):
            return self.delete_task(number)

        m = re.search(r"(?:delete|remove)\s+(?:task\s+)?(\d+)", cmd)
        if m:
            return self.delete_task(int(m.group(1)))

        if cmd in {"clear completed", "clear completed tasks",
                   "remove completed tasks", "completed tasks हटाओ",
                   "completed task हटाओ"}:
            return self.clear_completed_tasks()

        rule = self.extract_after_prefix(cmd, [
            "add rule ", "add a rule ", "new rule ", "remember rule ",
            "rule add ", "रूल जोड़ो ", "नियम जोड़ो ", "रूल ऐड करो "
        ])
        if rule:
            return self.add_rule(rule)

        m = re.match(r"(?:delete|remove)\s+(?:rule\s+)?(\d+)\s*$", cmd)
        if m:
            return self.delete_rule(int(m.group(1)))

        m = re.match(r"(?:add|set|create)\s+(?:timetable|schedule)\s+"
                     r"(\d{1,2}:\d{2})\s+(.+)$", cmd)
        if m:
            if self.valid_time(m.group(1)):
                key = self.normalize_time(m.group(1))
                self.data["timetable"][key] = m.group(2).strip()
                self.save_data()
                return self.show_timetable()
            return "Invalid time. Use HH:MM, for example 18:30."

        # Hindi/Hinglish timetable: "टाइमटेबल में 19:00 coding जोड़ो"
        m = re.search(r"(?:timetable|टाइमटेबल).{0,15}"
                      r"(\d{1,2}:\d{2}).{0,10}(.+)", cmd)
        if m and any(x in cmd for x in ["add", "set", "जोड़", "ऐड"]):
            if self.valid_time(m.group(1)):
                self.data["timetable"][self.normalize_time(m.group(1))] = m.group(2).strip()
                self.save_data()
                return self.show_timetable()

        return (
            "I don't understand that command yet. "
            "Say 'VYRo help' for commands."
        )

    @staticmethod
    def extract_after_prefix(command, prefixes):
        for prefix in prefixes:
            if command.startswith(prefix):
                value = command[len(prefix):].strip()
                if value:
                    return value
        return None

    @staticmethod
    def extract_number(command, words):
        for word in words:
            m = re.search(r"\b" + re.escape(word) +
                          r"\s+(?:task\s+)?(\d+)\b", command)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def valid_time(value):
        try:
            h, m = map(int, value.split(":"))
            return 0 <= h <= 23 and 0 <= m <= 59
        except Exception:
            return False

    @staticmethod
    def normalize_time(value):
        h, m = map(int, value.split(":"))
        return f"{h:02d}:{m:02d}"

    def add_task(self, task):
        self.data["tasks"].append({
            "task": task,
            "completed": False,
            "created": datetime.now().strftime("%d-%m-%Y %I:%M %p")
        })
        self.save_data()
        return f"Task added: {task}"

    def complete_task(self, number):
        i = number - 1
        if not 0 <= i < len(self.data["tasks"]):
            return f"Task {number} does not exist."
        self.data["tasks"][i]["completed"] = True
        self.save_data()
        return f"Task completed: {self.data['tasks'][i]['task']}"

    def delete_task(self, number):
        i = number - 1
        if not 0 <= i < len(self.data["tasks"]):
            return f"Task {number} does not exist."
        removed = self.data["tasks"].pop(i)
        self.save_data()
        return f"Task deleted: {removed['task']}"

    def clear_completed_tasks(self):
        before = len(self.data["tasks"])
        self.data["tasks"] = [x for x in self.data["tasks"] if not x.get("completed")]
        self.save_data()
        return f"Removed {before - len(self.data['tasks'])} completed task(s)."

    def add_rule(self, rule):
        self.data["rules"].append(rule)
        self.save_data()
        return f"Rule added: {rule}"

    def delete_rule(self, number):
        i = number - 1
        if not 0 <= i < len(self.data["rules"]):
            return f"Rule {number} does not exist."
        removed = self.data["rules"].pop(i)
        self.save_data()
        return f"Rule deleted: {removed}"

    def show_rules(self):
        return "DAILY RULES\n\n" + "\n".join(
            f"{i}. {x}" for i, x in enumerate(self.data["rules"], 1)
        )

    def show_timetable(self):
        return "DAILY TIMETABLE\n\n" + "\n".join(
            f"{t}  ->  {a}"
            for t, a in sorted(self.data["timetable"].items())
        )

    def show_tasks(self):
        if not self.data["tasks"]:
            return "TASKS\n\nNo tasks yet."
        return "TASKS\n\n" + "\n".join(
            f"{i}. {'[DONE]' if x.get('completed') else '[ ]'} {x['task']}"
            for i, x in enumerate(self.data["tasks"], 1)
        )

    def show_summary(self):
        done = sum(1 for x in self.data["tasks"] if x.get("completed"))
        pending = len(self.data["tasks"]) - done
        return (
            "DAILY SUMMARY\n\n"
            f"Date: {datetime.now().strftime('%A, %d %B %Y')}\n"
            f"Time: {datetime.now().strftime('%I:%M %p')}\n\n"
            f"Rules: {len(self.data['rules'])}\n"
            f"Completed tasks: {done}\n"
            f"Pending tasks: {pending}\n"
            f"Timetable entries: {len(self.data['timetable'])}"
        )

    @staticmethod
    def help_text():
        return (
            "VYRo COMMAND CENTER\n\n"
            "TIME: what time is it / समय क्या है\n"
            "DATE: today's date / आज की तारीख क्या है\n"
            "RULES: show my rules / मेरे रूल्स दिखाओ\n"
            "TIMETABLE: show my timetable / मेरा टाइमटेबल दिखाओ\n"
            "TASKS: show my tasks / मेरे टास्क दिखाओ\n"
            "ADD TASK: add task finish Python project\n"
            "COMPLETE: complete task 1\n"
            "DELETE: delete task 1\n"
            "ADD RULE: add rule study 2 hours\n"
            "SUMMARY: daily summary"
        )
