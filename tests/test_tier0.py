"""Tests for arbor.tier0 — dedup collapse + request budget estimation."""
import json


class TestNormalizeKey:
    def test_plain(self):
        from arbor.tier0 import normalize_key
        assert normalize_key("report.pdf") == "report"

    def test_strips_date(self):
        from arbor.tier0 import normalize_key
        k1 = normalize_key("report_2025-03-14.pdf")
        k2 = normalize_key("report_2025-03-15.pdf")
        assert k1 == k2 == "report"

    def test_strips_version(self):
        from arbor.tier0 import normalize_key
        assert normalize_key("data_v2.csv") == normalize_key("data_v3.csv")

    def test_strips_copy(self):
        from arbor.tier0 import normalize_key
        assert normalize_key("config_copy.pdf") == normalize_key("config.pdf")

    def test_strips_branch_code(self):
        from arbor.tier0 import normalize_key
        assert normalize_key("file_B12345.pdf") == normalize_key("file_B99999.pdf")

    def test_strips_trailing_digits(self):
        from arbor.tier0 import normalize_key
        assert normalize_key("log_123456.txt") == normalize_key("log_789012.txt")

    def test_case_insensitive(self):
        from arbor.tier0 import normalize_key
        assert normalize_key("Report.pdf") == normalize_key("REPORT.PDF")

    def test_deep_path(self):
        from arbor.tier0 import normalize_key
        # Only basename matters
        assert normalize_key("a/b/report.pdf") == "report"


class TestBuildLogicalFiles:
    def test_exact_dupes_dropped(self, case_config, tmp_path):
        from arbor.inventory import normalize_inventory
        from arbor.tier0 import build_logical_files
        data = normalize_inventory({
            "dirs": ["a/", "b/"],
            "files": {
                "a/report.pdf": {"size": 1000},
                "b/report.pdf": {"size": 1000},  # exact dupe
            },
        })
        logical, stats, top = build_logical_files(case_config, data)
        assert stats["raw_files"] == 2
        assert stats["logical_files"] == 1
        assert stats["exact_dupe_groups"] == 1

    def test_near_dupes_dropped(self, case_config, tmp_path):
        from arbor.inventory import normalize_inventory
        from arbor.tier0 import build_logical_files
        data = normalize_inventory({
            "dirs": [],
            "files": {
                "report_2025-01-01.pdf": {"size": 1000},
                "report_2025-01-02.pdf": {"size": 2000},  # near dupe (different size)
                "unique.doc": {"size": 500},
            },
        })
        logical, stats, top = build_logical_files(case_config, data)
        assert stats["near_dupe_groups"] >= 1

    def test_no_dupes(self, case_config, tmp_path):
        from arbor.inventory import normalize_inventory
        from arbor.tier0 import build_logical_files
        data = normalize_inventory({
            "dirs": [],
            "files": {"a.pdf": {"size": 1}, "b.doc": {"size": 2}},
        })
        logical, stats, top = build_logical_files(case_config, data)
        assert stats["logical_files"] == 2
        assert stats["total_dropped"] == 0

    def test_reduction_pct(self, case_config, tmp_path):
        from arbor.inventory import normalize_inventory
        from arbor.tier0 import build_logical_files
        data = normalize_inventory({
            "dirs": [],
            "files": {
                "x.pdf": {"size": 10},
                "x.pdf_copy": {"size": 10},  # won't be exact dupe (different name)
            },
        })
        logical, stats, top = build_logical_files(case_config, data)
        assert stats["reduction_pct"] >= 0.0
        assert stats["reduction_pct"] <= 100.0


class TestTier0All:
    def test_output_json(self, case_config, tmp_path):
        from arbor.inventory import normalize_inventory
        from arbor.tier0 import tier0_all
        data = normalize_inventory({
            "dirs": ["a/"],
            "files": {"a/f.pdf": {"size": 100}},
        })
        inv_path = tmp_path / "inv.json"
        inv_path.write_text(json.dumps(data))
        case_config.inventory = inv_path
        case_config.output_dir.mkdir(parents=True, exist_ok=True)
        path = tier0_all(case_config)
        result = json.load(open(path))
        assert "stats" in result
        assert "request_budget_rows_per_request" in result
        assert result["stats"]["raw_files"] == 1
        budget = result["request_budget_rows_per_request"]
        assert budget["50"] >= 1
