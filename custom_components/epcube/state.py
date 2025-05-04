from datetime import date

class EpCubeDataState:
    def __init__(self):
        self.charge_total = 0.0
        self.discharge_total = 0.0
        self.last_battery_energy = None
        self.last_reset = date.today()

    def update(self, battery_now: float):
        today = date.today()

        if today != self.last_reset:
            self.charge_total = 0.0
            self.discharge_total = 0.0
            self.last_reset = today
            self.last_battery_energy = battery_now
            return

        if self.last_battery_energy is None:
            self.last_battery_energy = battery_now
            return

        delta = battery_now - self.last_battery_energy
        if delta > 0:
            self.charge_total += delta
        elif delta < 0:
            self.discharge_total += abs(delta)

        self.last_battery_energy = battery_now
