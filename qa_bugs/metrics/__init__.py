from .defect_age import DefectAge
from .age_by_priority import AgeByPriority
from .cumulative_open_closed import CumulativeOpenClosed
from .leakage_rate import LeakageRate

METRICS = {
    "defect_age": DefectAge,
    "age_by_priority": AgeByPriority,
    "cumulative_open_closed": CumulativeOpenClosed,
    "leakage_rate": LeakageRate,
}
