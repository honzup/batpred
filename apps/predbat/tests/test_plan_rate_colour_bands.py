# -----------------------------------------------------------------------------
# Predbat Home Battery System
# Copyright Trefor Southwell 2026 - All Rights Reserved
# This application maybe used for personal use only and not for commercial use
# -----------------------------------------------------------------------------
# fmt off
# pylint: disable=consider-using-f-string
# pylint: disable=line-too-long
# pylint: disable=attribute-defined-outside-init

from prediction import Prediction
from tests.test_infra import reset_inverter, reset_rates

BLUE = "#74C1FF"
GREEN = "#3AEE85"
YELLOW = "#FFFFAA"
RED = "#F18261"
LIGHT_BLUE = "#48deff"
GREY = "#dcdcdc"


def check_colours(name, colour_function, threshold, cases):
    """
    Check colour_function(rate, threshold) against a list of (rate, expected colour), returns True on failure
    """
    failed = False
    for rate, expected in cases:
        got = colour_function(rate, threshold)
        if got != expected:
            print("ERROR: {} rate {} threshold {} expected {} got {}".format(name, rate, threshold, expected, got))
            failed = True
    return failed


def set_bands(my_predbat, import_bands, export_bands):
    """
    Set (or remove) the colour band apps.yaml keys and re-read the configuration
    """
    for name, value in (("plan_rate_colour_bands", import_bands), ("plan_export_colour_bands", export_bands)):
        if value is None:
            my_predbat.args.pop(name, None)
        else:
            my_predbat.args[name] = value
    my_predbat.fetch_config_options()


def run_test_plan_rate_colour_bands(my_predbat):
    """
    Test the optional fixed plan_rate_colour_bands / plan_export_colour_bands colouring of the plan rates
    """
    print("**** Running plan rate colour bands tests ****")
    failed = False
    my_predbat.load_user_config()

    # Unset - threshold based colours exactly as before (threshold 20: green <= 20, red > 30)
    set_bands(my_predbat, None, None)
    if my_predbat.plan_rate_colour_bands is not None or my_predbat.plan_export_colour_bands is not None:
        print("ERROR: colour bands should be None when not configured")
        failed = True
    failed |= check_colours("import default", my_predbat.plan_import_rate_color, 20, [(-1, BLUE), (0, BLUE), (10, GREEN), (20, GREEN), (25, YELLOW), (30, YELLOW), (30.01, RED), (500, RED)])
    failed |= check_colours("export default", my_predbat.plan_export_rate_color, 20, [(30, RED), (29.9, YELLOW), (20, YELLOW), (10.01, LIGHT_BLUE), (10, GREY), (0, GREY)])

    # Import bands set, export unset - export keeps the threshold based colours
    set_bands(my_predbat, [200, 400], None)
    if my_predbat.plan_rate_colour_bands != (200.0, 400.0):
        print("ERROR: plan_rate_colour_bands expected (200.0, 400.0) got {}".format(my_predbat.plan_rate_colour_bands))
        failed = True
    # The threshold (384) must be ignored for import when the bands are set
    failed |= check_colours("import bands", my_predbat.plan_import_rate_color, 384, [(-5, BLUE), (0, BLUE), (1, GREEN), (200, GREEN), (200.01, YELLOW), (400, YELLOW), (400.01, RED), (500, RED)])
    failed |= check_colours("export default with import bands", my_predbat.plan_export_rate_color, 20, [(30, RED), (20, YELLOW), (10.01, LIGHT_BLUE), (10, GREY)])

    # Export bands set
    set_bands(my_predbat, [200, 400], [50, 150])
    failed |= check_colours("export bands", my_predbat.plan_export_rate_color, 20, [(151, RED), (150, RED), (149.9, YELLOW), (50, YELLOW), (49.9, LIGHT_BLUE), (0.01, LIGHT_BLUE), (0, GREY), (-3, GREY)])

    # Invalid values fall back to the default colours, with one warning per key
    for bad in [[400, 200], [200], [200, 400, 600], ["low", 400], [True, 400], 300, "200,400"]:
        my_predbat.rate_colour_bands_warned = set()
        set_bands(my_predbat, bad, bad)
        if my_predbat.plan_rate_colour_bands is not None or my_predbat.plan_export_colour_bands is not None:
            print("ERROR: invalid colour bands {} should be ignored".format(bad))
            failed = True
        if my_predbat.rate_colour_bands_warned != {"plan_rate_colour_bands", "plan_export_colour_bands"}:
            print("ERROR: invalid colour bands {} should warn for both keys, warned {}".format(bad, my_predbat.rate_colour_bands_warned))
            failed = True
        failed |= check_colours("import invalid {}".format(bad), my_predbat.plan_import_rate_color, 20, [(20, GREEN), (25, YELLOW), (31, RED)])

    # End to end - the published plan rows use the bands (import 300 = yellow, export 160 = red)
    set_bands(my_predbat, [200, 400], [50, 150])
    reset_inverter(my_predbat)
    my_predbat.forecast_minutes = 24 * 60
    my_predbat.end_record = 24 * 60
    my_predbat.soc_max = 10.0
    my_predbat.soc_kw = 5.0
    pv_step = {}
    load_step = {}
    for minute in range(0, my_predbat.forecast_minutes, 5):
        pv_step[minute] = 0
        load_step[minute] = 0.5 / (60 / 5)
    my_predbat.prediction = Prediction(my_predbat, pv_step, pv_step, load_step, load_step)
    reset_rates(my_predbat, 300.0, 160.0)
    my_predbat.rate_best_cost_threshold_charge = 1000
    my_predbat.run_prediction([], [], [], [], False, end_record=my_predbat.end_record, save="best")
    my_predbat.charge_limit_best = []
    my_predbat.export_limits_best = []
    my_predbat.charge_window_best = []
    my_predbat.export_window_best = []
    html_plan, raw_plan = my_predbat.publish_html_plan(pv_step, pv_step, load_step, load_step, my_predbat.end_record, publish=False)
    rows = raw_plan.get("rows", [])
    if not rows:
        print("ERROR: raw_plan has no rows")
        failed = True
    for row in rows:
        if row.get("rate_color_import") != YELLOW or row.get("rate_color_export") != RED:
            print("ERROR: plan row {} expected import {} export {} got {} {}".format(row.get("time"), YELLOW, RED, row.get("rate_color_import"), row.get("rate_color_export")))
            failed = True
            break

    set_bands(my_predbat, None, None)
    if not failed:
        print("All plan rate colour bands tests passed")
    return failed
