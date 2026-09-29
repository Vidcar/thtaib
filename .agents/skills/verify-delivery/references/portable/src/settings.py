"""Deliberately incomplete exercise fixture; never application code."""


def draft(value, notes):
    return {"value": value, "notes": notes}


def execution(value):
    return {"value": value}


class Controls:
    def __init__(self):
        self.selected = 10
        self.message = ""

    def apply(self, value, service):
        try:
            service.save(value)
            service.refresh()
            self.selected = value
        except RuntimeError as error:
            self.message = str(error)
