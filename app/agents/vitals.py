"""Vitals agent - weight, BMI, heart rate and blood pressure.

Reports readings and standard reference bands. It does not interpret them
as a diagnosis; out-of-range readings are pointed at a clinician.
"""
from app.agents.base import BaseAgent, AgentReply
from app.core.validation import bmi, bmi_band
from app.store import db


class VitalsAgent(BaseAgent):
    name = "vitals"
    description = "Tracks weight, BMI, heart rate and blood pressure readings."

    def handle(self, query: str) -> AgentReply:
        f = self.report()
        bits = []
        if f["weight_kg"]:
            bits.append(f"weight {f['weight_kg']} kg")
        if f["bmi"]:
            bits.append(f"BMI {f['bmi']} ({f['bmi_band']})")
        if f["heart_rate"]:
            bits.append(f"resting heart rate {f['heart_rate']} bpm")
        if f["blood_pressure"]:
            bits.append(f"blood pressure {f['blood_pressure']}")

        if not bits:
            text = ("No vitals logged yet. You can tell me your weight, "
                    "height, heart rate or blood pressure.")
        else:
            text = "Latest readings: " + ", ".join(bits) + "."
            if f["flags"]:
                text += (" " + " ".join(f["flags"]) +
                         " Worth mentioning to a doctor rather than acting on "
                         "it from here.")
        return AgentReply(agent=self.name, text=text, data=f)

    def _latest(self, metric: str) -> dict | None:
        rows = db.query(
            "SELECT value, secondary, day FROM vitals WHERE metric = ? "
            "ORDER BY id DESC LIMIT 1", (metric,))
        return rows[0] if rows else None

    def report(self) -> dict:
        weight = self._latest("weight_kg")
        height = self._latest("height_cm")
        hr = self._latest("heart_rate")
        bp = self._latest("systolic")

        body_mass = None
        band = ""
        if weight and height:
            body_mass = bmi(weight["value"], height["value"])
            band = bmi_band(body_mass)

        flags = []
        if hr and (hr["value"] > 100 or hr["value"] < 50):
            flags.append("That resting heart rate is outside the typical "
                         "60-100 bpm range.")
        if bp and (bp["value"] >= 140 or (bp["secondary"] or 0) >= 90):
            flags.append("That blood pressure reading is above the usual "
                         "reference range.")

        return {
            "has_data": bool(weight or height or hr or bp),
            "weight_kg": weight["value"] if weight else None,
            "height_cm": height["value"] if height else None,
            "bmi": body_mass,
            "bmi_band": band,
            "heart_rate": hr["value"] if hr else None,
            "blood_pressure": (f"{int(bp['value'])}/{int(bp['secondary'])}"
                               if bp and bp["secondary"] else None),
            "flags": flags,
            "status": "attention" if flags else "ok",
        }
