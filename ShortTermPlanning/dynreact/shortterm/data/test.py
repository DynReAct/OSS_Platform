"""
test.py
This scripts checks the data returned by the functions.
"""
from data.data_functions import get_equipment_materials, get_equipment_status, get_material_params, get_transition_cost_and_status
import json


if __name__ == "__main__":

    # Notes: the ID of VEA08 is 14; the ID of VEA09 is 15
    resource1 = 14
    resource2 = 15
    material1 = '1003941106'

    resource1_materials = get_equipment_materials(resource1)
    print(f"---- Resource {resource1}'s materials:", resource1_materials)
    resource1_status = get_equipment_status(resource1)
    print(f"---- Resource {resource1} status:", resource1_status)

    resource2_materials = get_equipment_materials(resource2)
    print(f"---- Resource {resource2}'s materials:", resource2_materials)
    resource2_status = get_equipment_status(resource2)
    print(f"---- Resource {resource2} status:", resource2_status)

    material1_params = get_material_params(material1)
    print(f"---- Material {material1}:", material1_params)

    print(f"---- Resource {resource1}'s transition from {resource1_status['current_coils'][-1]} to {material1}")
    transition = get_transition_cost_and_status(material_params=material1_params, resource_status=resource1_status)
    print(f"Result:")
    print(json.dumps(transition, indent=4))

    # material2 = '1003933326'
    # material2_params = get_material_params(material2)
    # print(f"---- Material {material2}:", material2_params)
    # print(f"---- Resource {resource1}'s transition from {material1} to {material2}:")
    # resource1_status = transition[1]
    # transition = get_transition_cost_and_status(material_params=material2_params, resource_status=resource1_status)

    print(f"==== TRANSITIONS OF RESOURCE {resource1} TO EVERY MATERIAL OF ITS LIST")
    resource1_allowed_materials = []
    for resource_material in resource1_materials:
        print(
            f"---- Resource {resource1}'s transition from {resource1_status['current_coils'][-1]} to {resource_material}")
        resource_material_params = get_material_params(resource_material)
        transition = get_transition_cost_and_status(material_params=resource_material_params,
                                                    resource_status=resource1_status)
        if transition[0] is not None:
            resource1_allowed_materials.append(resource_material)

    print(f"==== TRANSITIONS OF RESOURCE {resource1} TO EVERY MATERIAL OF RESOURCE {resource2}")
    for resource_material in resource2_materials:
        print(
            f"---- Resource {resource1}'s transition from {resource1_status['current_coils'][-1]} to {resource_material}")
        resource_material_params = get_material_params(resource_material)
        transition = get_transition_cost_and_status(material_params=resource_material_params,
                                                    resource_status=resource1_status)
        if transition[0] is not None:
            resource1_allowed_materials.append(resource_material)

    print(f"==== TRANSITIONS OF RESOURCE {resource2} TO EVERY MATERIAL OF ITS LIST")
    resource2_allowed_materials = []
    for resource_material in resource2_materials:
        print(
            f"---- Resource {resource2}'s transition from {resource2_status['current_coils'][-1]} to {resource_material}")
        resource_material_params = get_material_params(resource_material)
        transition = get_transition_cost_and_status(material_params=resource_material_params,
                                                    resource_status=resource2_status)
        if transition[0] is not None:
            resource2_allowed_materials.append(resource_material)

    print(f"==== TRANSITIONS OF RESOURCE {resource2} TO EVERY MATERIAL OF RESOURCE {resource1}")
    for resource_material in resource1_materials:
        print(
            f"---- Resource {resource2}'s transition from {resource2_status['current_coils'][-1]} to {resource_material}")
        resource_material_params = get_material_params(resource_material)
        transition = get_transition_cost_and_status(material_params=resource_material_params,
                                                    resource_status=resource2_status)
        if transition[0] is not None:
            resource2_allowed_materials.append(resource_material)

    print(f"Resource {resource1} allowed materials:", resource1_allowed_materials)
    print(f"Resource {resource2} allowed materials:", resource2_allowed_materials)
