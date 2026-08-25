import json
import unittest
from pathlib import Path

from shadowbane_lab.protocol import encode_message

from tests.fixtures import protocol_exchange

try:
    import jsonschema
except ImportError:  # The dependency-free local contract tests still run without this extra.
    jsonschema = None


SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "protocol-v1.schema.json"


class ProtocolSchemaTests(unittest.TestCase):
    def test_schema_is_valid_json(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(4, len(schema["oneOf"]))

    @unittest.skipIf(jsonschema is None, "jsonschema test extra is not installed")
    def test_every_fixture_matches_the_wire_schema(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator_class = jsonschema.validators.validator_for(schema)
        validator_class.check_schema(schema)
        validator = validator_class(schema)

        for message in protocol_exchange():
            with self.subTest(message=type(message).__name__):
                validator.validate(json.loads(encode_message(message)))


if __name__ == "__main__":
    unittest.main()
