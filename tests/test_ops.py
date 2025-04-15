import os
import pandas as pd
from pipeline.ops.aggregate import aggregate_reports

# Create a dummy context with a minimal logger implementation.
class DummyLogger:
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass

class DummyContext:
    def __init__(self):
        self.log = DummyLogger()

def test_aggregate_reports(tmp_path):
    # Create an output folder inside the temporary directory.
    output_folder = tmp_path / "output"
    output_folder.mkdir()

    # Create two dummy report files.
    report1 = output_folder / "test1.txt"
    report1.write_text("Report text for test1.")
    report2 = output_folder / "test2.txt"
    report2.write_text("Report text for test2.")

    # Prepare the list of report entries as expected by the aggregation function.
    reports = [
        {"wsi_name": "test1", "report_path": str(report1)},
        {"wsi_name": "test2", "report_path": str(report2)}
    ]
    config_dict = {"output_folder": str(output_folder)}

    dummy_context = DummyContext()

    # Call the aggregation function.
    aggregate_reports(dummy_context, reports, config_dict)

    # Verify that the CSV "results.csv" exists and contains the expected data.
    csv_path = os.path.join(str(output_folder), "results.csv")
    assert os.path.exists(csv_path)
    
    df = pd.read_csv(csv_path)
    # Expect two rows for the two reports.
    assert df.shape[0] == 2
    assert "wsi_name" in df.columns
    assert "report_text" in df.columns
