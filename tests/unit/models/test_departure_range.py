from datetime import datetime

import pytest

from tests.unit.price_source.fixtures import WARSAW
from train_ticket_prices.models import DepartureRange


@pytest.mark.unit
@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 11, 23, 5, 59, tzinfo=WARSAW), False),
        (datetime(2026, 11, 23, 6, 0, tzinfo=WARSAW), True),
        (datetime(2026, 11, 23, 12, 0, tzinfo=WARSAW), True),
        (datetime(2026, 11, 23, 12, 1, tzinfo=WARSAW), False),
    ],
)
def test_contains_is_inclusive(*, moment: datetime, expected: bool) -> None:
    departure = DepartureRange(
        start=datetime(2026, 11, 23, 6, 0, tzinfo=WARSAW),
        end=datetime(2026, 11, 23, 12, 0, tzinfo=WARSAW),
    )

    assert departure.contains(moment) is expected


@pytest.mark.unit
def test_naive_bounds_are_read_as_warsaw_time() -> None:
    departure = DepartureRange(
        start=datetime(2026, 11, 23, 6, 0),  # noqa: DTZ001
        end=datetime(2026, 11, 23, 12, 0),  # noqa: DTZ001
    )

    assert departure.start == datetime(2026, 11, 23, 6, 0, tzinfo=WARSAW)
    assert departure.contains(datetime(2026, 11, 23, 7, 0, tzinfo=WARSAW))
