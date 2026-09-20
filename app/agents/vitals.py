"""
Vitals agent - body measurements the user enters themselves.

Nothing here is measured by the app. There is no wearable, no sensor and
no camera trick: every figure is a reading the user typed in, taken from
a weighing scale, a tape measure, a home blood-pressure monitor, or a
clinic visit. The interface says so, because a number presented as though
the phone measured it would be a lie.

BMI is the exception, and only because it is arithmetic: given a height
and a weight the user supplied, the app computes it rather than asking.
"""
from app.agents.base import BaseAgent, AgentReply
from app.core.validation import bmi, bmi_band
from app.store import db

# Standard adult reference ranges, used to flag a reading as worth
# mentioning to a clinician. Not used to diagnose anything.
HR_NORMAL = (60, 100)
BP_RAISED = (140, 90)


class VitalsAgent(BaseAgent):
    name = "vitals"
    description = (
        "Holds self-reported body measurements: height, weight, blood "
        "pressure and resting heart rate. Computes BMI from height and "
        "weight. Measures nothing itself."
    )

    def handle(self, query: str) -> AgentReply:
        f = self.report()
        bits = []
        if f["weight_kg"]:
            bits.append(f"weight {f['weight_kg']:g} kg")
        if f["bmi"]:
            bits.append(f"BMI {f['bmi']} ({f['bmi_band']})")
        if f["heart_rate"]:
            bits.append(f"resting heart rate {f['heart_rate']:g} bpm")
        if f["blood_pressure"]:
            bits.append(f"blood pressure {f['blood_pressure']}")

        if not bits:
            return AgentReply(
                agent=self.name,
                text="No measurements yet. I cannot measure anything myself, "
                     "so tell me your height and weight and I will work out "
                     "your BMI. You can also give me a blood pressure or "
                     "heart rate reading from a monitor.",
                data=f)

        text = "Your last readings: " + ", ".join(bits) + "."
        if f["missing_for_bmi"]:
            text += f" Give me your {f['missing_for_bmi']} and I can work out your BMI."
        if f["flags"]:
            text += (" " + " ".join(f["flags"]) +
                     " That is worth mentioning to a doctor rather than "
                     "acting on from here.")
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

        body_mass, band = None, ""
        if weight and height:
            body_mass = bmi(weight["value"], height["value"])
            band = bmi_band(body_mass)

        missing = ""
        if weight and not height:
            missing = "height"
        elif height and not weight:
            missing = "weight"

        flags = []
        if hr and not (HR_NORMAL[0] <= hr["value"] <= HR_NORMAL[1]):
            flags.append(f"That resting heart rate is outside the usual "
                         f"{HR_NORMAL[0]} to {HR_NORMAL[1]} bpm range.")
        if bp and (bp["value"] >= BP_RAISED[0]
                   or (bp["secondary"] or 0) >= BP_RAISED[1]):
            flags.append("That blood pressure reading is above the usual "
                         "reference range.")

        return {
            "has_data": bool(weight or height or hr or bp),
            "self_reported": True,     # nothing here is measured by the app
            "weight_kg": weight["value"] if weight else None,
            "height_cm": height["value"] if height else None,
            "bmi": body_mass,
            "bmi_band": band,
            "missing_for_bmi": missing,
            "heart_rate": hr["value"] if hr else None,
            "heart_rate_on": hr["day"] if hr else None,
            "blood_pressure": (f"{int(bp['value'])}/{int(bp['secondary'])}"
                               if bp and bp["secondary"] else None),
            "blood_pressure_on": bp["day"] if bp else None,
            "flags": flags,
            "status": "attention" if flags else "ok",
        }
