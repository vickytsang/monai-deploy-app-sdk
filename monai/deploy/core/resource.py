# Copyright 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Optional, Union

from monai.deploy.exceptions import ItemAlreadyExistsError, UnknownTypeError, UnsupportedOperationError


class Resource:
    """Class responible for resource limits.

    Each resource limit value is None (its access would return 0) and the value is overriden by @resource decorator
    and then by the CLI arguments.

    To do so, first, each resource limit value is set to None unless those values are set by the CLI arguments.
    Then, if the resource limit value is None and the user specifies a value through @resource decorator,
    the value is set to the given attribute.
    """

    def __init__(self, cpu: Optional[int] = None, memory: Optional[int] = None, gpu: Optional[int] = None):
        self._cpu = cpu
        self._memory = memory
        self._gpu = gpu

    @property
    def cpu(self) -> int:
        if self._cpu is None:
            return 0
        return self._cpu

    @property
    def memory(self) -> int:
        if self._memory is None:
            return 0
        return self._memory

    @property
    def gpu(self) -> int:
        # TODO(gigony): check if the gpu limit can be distinguished between all gpus vs zero gpu.
        #               https://github.com/NVIDIA/k8s-device-plugin/issues/61
        if self._gpu is None:
            return 0
        return self._gpu

    def set_resource_limits(
        self,
        cpu_limit: Optional[int] = None,
        memory_limit: Optional[Union[int, str]] = None,
        gpu_limit: Optional[int] = None,
    ):
        """Sets resource limits from the given values if each attribute is not None."""

        if cpu_limit is not None:
            if self._cpu is None:
                self._cpu = cpu_limit
            else:
                raise ItemAlreadyExistsError(
                    f"'cpu' wouldn't be set to {cpu_limit} because it is already set to {self._cpu} by the runtime environment."
                )

        if gpu_limit is not None:
            if self._gpu is None:
                self._gpu = gpu_limit
            else:
                raise ItemAlreadyExistsError(
                    f"'gpu' wouldn't be set to {gpu_limit} because it is already set to {self._gpu} by the runtime environment."
                )

        if type(memory_limit) == str:
            # TODO(gigony): convert str to int
            raise UnsupportedOperationError("Memory limit must be an integer.")
        else:
            if memory_limit is not None:
                if self._memory is None:
                    self._memory = memory_limit
                else:
                    raise ItemAlreadyExistsError(
                        f"'memory' wouldn't be set to {memory_limit} because it is already set to {self._memory}"
                        " by the runtime environment."
                    )

    def __str__(self):
        return "Resource(cpu={}, memory={}, gpu={})".format(self.cpu, self.memory, self.gpu)


def resource(
    cpu: Optional[int] = None,
    memory: Optional[Union[int, str]] = None,
    gpu: Optional[int] = None,
):
    """A decorator that adds an resource requirement to the application.

    Args:
        cpu (int): A number of CPU cores required.
        memory (int): A size of memory required (in bytes).
        gpu (int): A number of GPUs required.

    Returns:
        A decorator that adds an resource requirement to the application.
    """

    # Import here to avoid circular imports
    from .application import Application

    def decorator(cls):
        if issubclass(cls, Application):
            builder = cls.__dict__.get("_builder")
        else:
            raise UnknownTypeError("Use @resource decorator only for a subclass of Application!")

        def new_builder(self):
            if builder:
                builder(self)  # execute the original builder

            try:
                self.context.resource.set_resource_limits(cpu, memory, gpu)
            except ItemAlreadyExistsError as e:
                raise ItemAlreadyExistsError(f"In @resource decorator at {self.name}, {e.args[0]}")

            return self
        cls._builder = new_builder
        return cls

    return decorator
