from datetime import date

class EpCubeDataState:
    def __init__(self):
        self.last_battery_energy = None
        self.total_in = 0.0
        self.total_out = 0.0
        self.daily_in = 0.0
        self.daily_out = 0.0
        self.last_reset = date.today()

    def reset_daily(self):
        self.daily_in = 0.0
        self.daily_out = 0.0
        self.last_reset = date.today()

    def update(self, battery_now: float):
        today = date.today()
        if today != self.last_reset:
            self.reset_daily()

        if self.last_battery_energy is None:
            self.last_battery_energy = battery_now
            return

        delta = battery_now - self.last_battery_energy

        if delta > 0:
            self.total_in += delta
            self.daily_in += delta
        elif delta < 0:
            self.total_out += abs(delta)
            self.daily_out += abs(delta)

        self.last_battery_energy = battery_now

