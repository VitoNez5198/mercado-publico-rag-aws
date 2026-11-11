import yaml
from pathlib import Path


def cfn_constructor(loader, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


for tag in ["!Sub", "!Ref", "!GetAtt", "!Join", "!Select", "!Split", "!FindInMap", "!Base64", "!Equals", "!And", "!Or", "!Not", "!If", "!Condition"]:
    yaml.SafeLoader.add_constructor(tag, cfn_constructor)

template_path = Path("template.yaml")
with open(template_path, "r", encoding="utf-8") as f:
    template = yaml.safe_load(f)

print(f"Template successfully parsed: {template.get('AWSTemplateFormatVersion')}")
print(f"Transform: {template.get('Transform')}")
resources = template.get("Resources", {})
print(f"Found {len(resources)} Resources:")
for name, r in resources.items():
    print(f" - [{r.get('Type')}] {name}")

outputs = template.get("Outputs", {})
print(f"Found {len(outputs)} Outputs:")
for name in outputs.keys():
    print(f" - {name}")

