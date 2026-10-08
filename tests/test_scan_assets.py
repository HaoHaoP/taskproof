"""The asset scan is a push gate, so its rules have to be precise.

A false positive here blocks every push, which means the gate gets disabled and
the real leak ships anyway. The i18n-key case below was observed on the first
run of the generic rules against this repository.

The canary strings in this file are assembled at runtime rather than written out.
That is not cleverness for its own sake: a test that spelled them literally would
be flagged by the scanner it is testing -- and, worse, would put the very strings
the gate exists to catch into a public repository.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "tools"))

import scan_assets  # noqa: E402

#: Canaries, assembled so this file contains no matching literal.
PRIVATE_ADDR = "192" + ".168" + ".41.63"
TEN_ADDR = "10" + ".20" + ".30.40"
INTERNAL_HOST = "build-box" + "." + "corp"
INTERNAL_URL = "http://" + "jenkins" + "." + "corp" + "/job/x"
INTERNAL_LOOKALIKE = "service" + "." + "local"
CREDENTIAL = "api_key" + ' = "' + "abcd1234efgh" + '"'
KEY_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"


class GenericRulesTest(unittest.TestCase):
    def setUp(self):
        self.compiled = scan_assets.compile_patterns(scan_assets.GENERIC_PATTERNS)

    def labels(self, text):
        return [label for _, label, _ in scan_assets.scan_text(text, self.compiled)]

    def test_an_i18n_key_is_not_an_internal_hostname(self):
        # `service.local` is a translation key in the desktop app. Flagging it
        # blocked the first scan of this repository.
        self.assertEqual(self.labels("{{ t('" + INTERNAL_LOOKALIKE + "') }}"), [])
        self.assertEqual(
            self.labels('<span class="label">{{ t(\'' + INTERNAL_LOOKALIKE + "') }}</span>"), []
        )

    def test_a_real_internal_url_is_caught(self):
        self.assertIn("internal URL", self.labels("see " + INTERNAL_URL))
        self.assertIn("internal URL", self.labels("//wiki" + "." + "internal/page"))

    def test_a_host_assignment_is_caught(self):
        self.assertIn("internal host assignment", self.labels("host: " + INTERNAL_HOST))
        self.assertIn("internal host assignment", self.labels('hostname = "db' + "." + 'intranet"'))

    def test_a_private_address_is_caught(self):
        self.assertIn("private IPv4 address", self.labels("addr " + PRIVATE_ADDR))
        self.assertIn("private IPv4 address", self.labels("addr " + TEN_ADDR))

    def test_credentials_and_private_keys_are_caught(self):
        self.assertIn("credential assignment", self.labels(CREDENTIAL))
        self.assertIn("private key block", self.labels(KEY_HEADER))

    def test_ordinary_text_is_not_flagged(self):
        for line in (
            "taskproof run my-app \"fix the test\"",
            "the registry lives at ~/.taskproof/projects.toml",
            "verification passed with exit code 0",
            "http://127.0.0.1:8787/api/health",
        ):
            self.assertEqual(self.labels(line), [], line)


class ScanShapeTest(unittest.TestCase):
    def test_the_pattern_file_lives_outside_the_repository(self):
        # The whole design: the organisation-specific words must not be able to
        # end up in the repository, so their home is not in it. A scanner that
        # shipped the words would leak exactly what it is meant to protect.
        self.assertFalse(
            os.path.abspath(scan_assets.DEFAULT_PATTERN_FILE).startswith(
                os.path.abspath(scan_assets.REPO_ROOT) + os.sep
            )
        )

    def test_the_generic_rules_alone_are_never_a_no_op(self):
        # With no pattern file configured the scanner still returns the generic
        # rules, so "clean" always means something.
        self.assertTrue(scan_assets.GENERIC_PATTERNS)
        previous = os.environ.pop("TASKPROOF_ASSET_PATTERNS", None)
        try:
            patterns, _ = scan_assets.load_patterns()
        finally:
            if previous is not None:
                os.environ["TASKPROOF_ASSET_PATTERNS"] = previous
        self.assertGreaterEqual(len(patterns), len(scan_assets.GENERIC_PATTERNS))


class PatternFileTest(unittest.TestCase):
    def test_patterns_come_from_the_environment_when_set(self):
        import tempfile

        synthetic = "Acme" + "Widgets"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("# comment\n" + synthetic + "\n")
            path = handle.name
        try:
            os.environ["TASKPROOF_ASSET_PATTERNS"] = path
            patterns, source = scan_assets.load_patterns()
        finally:
            os.environ.pop("TASKPROOF_ASSET_PATTERNS", None)
            os.unlink(path)
        self.assertEqual(source, path)
        self.assertIn("pattern file: " + synthetic, patterns)
        compiled = scan_assets.compile_patterns(patterns)
        self.assertTrue(
            scan_assets.scan_text("we shipped " + synthetic.lower() + " today", compiled)
        )


if __name__ == "__main__":
    unittest.main()
