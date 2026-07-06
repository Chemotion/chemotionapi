"""JSON-Schema definitions for the LabIMotion generic-element structures.

``ALL_SCHEMAS`` lists the schema modules that must be imported so each schema registers
itself with :class:`SchemaRegistry` on import.
"""

ALL_SCHEMAS = ["schema_generic_segments", "schema_generic_element", "schema_generic_layer", "schema_generic_linked_element",
               "schema_select_options", "schema_properties", "schema_cond_field", "schema_flow_obj", "schema_field",
               "schema_generic_dataset"]
