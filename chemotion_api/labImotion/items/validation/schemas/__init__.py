"""JSON-Schema definitions for the LabIMotion generic-element structures.

``ALL_SCHEMAS`` lists the schema modules that must be imported so each schema registers
itself with :class:`SchemaRegistry` on import.
"""

ALL_SCHEMAS = ["schema_generc_segments", "schema_generc_element", "schema_generc_layer", "schema_generc_linked_element",
               "schema_select_options", "schema_properties", "schema_cond_field", "schema_flow_obj", "schema_field",
               "schema_generc_dataset"]
