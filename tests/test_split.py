import pandas as pd

from ingestion.common import INITIAL_BATCH, REPLAY_END
from ingestion.split_by_day import assign_batches


def test_history_goes_to_initial_batch_and_tail_is_dropped():
    orders = pd.DataFrame({
        "order_id": ["old", "edge", "day", "late"],
        "order_purchase_timestamp": [
            "2017-01-05 10:00:00", f"{INITIAL_BATCH} 23:59:59", "2018-08-05 08:00:00", "2018-09-03 08:00:00",
        ],
    })
    out = assign_batches(orders).set_index("order_id")["_batch"].to_dict()
    assert out == {"old": INITIAL_BATCH, "edge": INITIAL_BATCH, "day": "2018-08-05"}
    assert all(b <= REPLAY_END for b in out.values())
