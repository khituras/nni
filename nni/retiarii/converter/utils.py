# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from ..operation import Cell
from ..graph import Model, Node


def build_full_name(prefix, name, seq=None):
    if isinstance(name, list):
        name = '__'.join(name)
    if seq is None:
        return '{}__{}'.format(prefix, name)
    else:
        return '{}__{}{}'.format(prefix, name, str(seq))


def build_cand_name(name, label):
    return f'layerchoice_{label}_{name}'


def _convert_name(name: str) -> str:
    """
    Convert the names using separator '.' to valid variable name in code
    """
    return name.replace('.', '__')


def _extract_info_from_trace_node(trace_node):
    """
    Extract parameters from a trace node.

    Parameters
    ----------
    trace_node: torch._C.Value
    """
    input_shape = []
    output_shape = []

    inputs = list(trace_node.inputs())

    # cat input tensors are in a strange place
    if trace_node.kind() == 'aten::cat':
        input_shape = [input.type().sizes() for input in inputs[0].node().inputs()]
    else:
        for _input in inputs:
            input_type = _input.type()
            if input_type.kind() == 'TensorType':
                shape = input_type.sizes()
                if shape:
                    input_shape.append(shape)

    for _output in trace_node.outputs():
        output_type = _output.type()
        if output_type.kind() == 'TensorType':
            shape = output_type.sizes()
            if shape:
                output_shape.append(shape)

    shape_parameters = {
        'input_shape': input_shape,
        'output_shape': output_shape,
    }

    if trace_node.kind() == 'aten::cat':
        parameters = {'dim': inputs[1].toIValue()}
        return shape_parameters, parameters
    else:
        return shape_parameters, None


def is_layerchoice_node(ir_node: Node):
    if ir_node is not None and isinstance(ir_node.operation, Cell) and ir_node.operation.parameters.get('mutation') == 'layerchoice':
        return True
    else:
        return False


def get_full_name_by_scope_name(ir_model: Model, scope_names, prefix=''):
    full_name = prefix

    for last_scope in range(len(scope_names)):
        ir_node = ir_model.get_node_by_name(full_name)
        # check if it's layerchoice
        if is_layerchoice_node(ir_node):
            full_name = f'layerchoice_{ir_node.operation.parameters["label"]}_{scope_names[last_scope]}'
        else:
            full_name = build_full_name(full_name, scope_names[last_scope])

    return full_name


def match_node(ir_model: Model, torch_node, prefix=''):
    """
    Match the corresponding node of a torch._C.Value
    """
    scope_names = torch_node.scopeName().split('/')[-1].split('.')[1:]
    full_name = get_full_name_by_scope_name(ir_model, scope_names, prefix)
    # handle the case when node is not nn.Module, but directly used in forward()
    # Because name can't be directly matched, so I use a hacky way.
    # I match the first unshaped node of that kind
    graph = ir_model.graphs.get(full_name)
    if graph is not None:
        for node in graph.get_nodes_by_type(torch_node.kind()):
            if not node.operation.attributes['input_shape']:
                return node
        return None
    else:
        return ir_model.get_node_by_name(full_name)


def _without_shape_info(node: Node):
    return not node.operation.attributes['input_shape'] and not node.operation.attributes['output_shape']
