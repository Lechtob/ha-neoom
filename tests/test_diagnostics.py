import json

from neoom_connect import EnergyFlow, SiteConfiguration, State
from neoom_connect.diagnostics import diagnostic_report


def test_report_excludes_raw_sensitive_fields():
    config = SiteConfiguration.from_api(
        {
            "siteId": "private-site",
            "siteInfo": {"geoCoordinates": {"latitude": 42}},
            "energyFlow": {"dataPoints": {}},
            "token": "private-token",
            "things": {
                "private-device": {"name": "private-name", "type": "BATTERY", "dataPoints": {}}
            },
        }
    )
    flow = EnergyFlow({"POWER_GRID": State("POWER_GRID", 100)}, raw={"token": "private-token"})
    report = diagnostic_report(
        config,
        flow,
        {
            "private-device": {
                "SERIAL_NUMBER": State("SERIAL_NUMBER", 123456),
                "STATE_CODE": State("STATE_CODE", "private-value"),
            }
        },
    )
    assert "private" not in json.dumps(report)
    assert "123456" not in json.dumps(report)
    assert "latitude" not in json.dumps(report)
