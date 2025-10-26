from .defect_age import DefectAge
from .age_by_priority import AgeByPriority
from .cumulative_open_closed import CumulativeOpenClosed
from .leakage_rate import LeakageRate
from .status_by_severity import StatusBySeverity
from .rejection_rate import RejectionRate

METRICS = {
    "defect_age": DefectAge,
    "age_by_priority": AgeByPriority,
    "cumulative_open_closed": CumulativeOpenClosed,
    "leakage_rate": LeakageRate,
    "status_by_severity": StatusBySeverity,
    "rejection_rate": RejectionRate,
}
