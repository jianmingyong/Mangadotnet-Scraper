import inspect
from collections.abc import Callable, MutableMapping
from inspect import Parameter
from typing import Any, Literal, NotRequired, Protocol, TypedDict, cast

type ContainerRegistration = (
    ContainerTypeRegistration
    | ContainerInstanceRegistration
    | ContainerFactoryRegistration
)


class ContainerTypeRegistration(TypedDict):
    kind: Literal["type"]
    value: type[Any]
    singleton: bool
    instance: NotRequired[Any | None]


class ContainerInstanceRegistration(TypedDict):
    kind: Literal["instance"]
    instance: Any


class ContainerFactoryRegistration(TypedDict):
    kind: Literal["factory"]
    value: Callable[..., Any]
    singleton: bool
    instance: NotRequired[Any | None]


class ServiceProvider(Protocol):
    def get[T](self, type: type[T], *args, **kwargs) -> T | None: ...

    def get_required[T](self, type: type[T], *args, **kwargs) -> T: ...


class ServiceCollection:
    _registration: MutableMapping[type[Any], ContainerRegistration]

    def __init__(self) -> None:
        self._registration = {}

    def register(
        self,
        implementation: type[Any] | Any | Callable[[ServiceProvider], Any],
        interface: type[Any] | None = None,
        singleton: bool = True,
    ) -> None:
        if implementation is None:
            raise TypeError("implementation must not be null")

        if interface is None:
            if not isinstance(implementation, type) and callable(
                implementation
            ):
                raise TypeError(
                    "callable factories requires interface declaration"
                )

            interface = (
                implementation
                if isinstance(implementation, type)
                else type(implementation)
            )

        if isinstance(implementation, type):
            self._registration[interface] = {
                "kind": "type",
                "value": implementation,
                "singleton": singleton,
            }
        elif callable(implementation):
            self._registration[interface] = {
                "kind": "factory",
                "value": implementation,
                "singleton": singleton,
            }
        else:
            self._registration[interface] = {
                "kind": "instance",
                "instance": implementation,
            }

    def get[T](self, type: type[T], *args, **kwargs) -> T | None:
        registration = self._registration.get(type)

        if registration is None:
            return None

        if registration["kind"] == "type":
            if registration["singleton"]:
                if registration["instance"] is None:
                    registration["instance"] = self._create_instance(
                        registration["value"]
                    )
                    return registration["instance"]
                else:
                    return registration["instance"]
            else:
                return self._create_instance(registration["value"])
        elif registration["kind"] == "instance":
            return registration["instance"]
        else:
            if registration["singleton"]:
                if registration["instance"] is None:
                    registration["instance"] = registration["value"](
                        self, *args, **kwargs
                    )
                    return registration["instance"]
                else:
                    return registration["instance"]
            else:
                return registration["value"](self, *args, **kwargs)

    def get_required[T](self, type: type[T], *args, **kwargs) -> T:
        registration = self._registration.get(type)

        if registration is None:
            raise ValueError("type is not registered as a service")

        if registration["kind"] == "type":
            if registration["singleton"]:
                if (
                    "instance" not in registration
                    or registration["instance"] is None
                ):
                    registration["instance"] = self._create_instance(
                        registration["value"]
                    )
                    return cast(T, registration["instance"])
                else:
                    return registration["instance"]
            else:
                return self._create_instance(registration["value"])
        elif registration["kind"] == "instance":
            return registration["instance"]
        else:
            if registration["singleton"]:
                if (
                    "instance" not in registration
                    or registration["instance"] is None
                ):
                    registration["instance"] = registration["value"](
                        self, *args, **kwargs
                    )
                    return cast(T, registration["instance"])
                else:
                    return registration["instance"]
            else:
                return registration["value"](self, *args, **kwargs)

    def _create_instance(
        self, implementation: type[Any], *args, **kwargs
    ) -> Any:
        constructor = inspect.signature(implementation.__init__)
        parameters = constructor.parameters
        new_args: list[Any] = []
        args_length = len(args)
        args_pos = 0

        for name, param in list(parameters.items())[1:]:
            if param.kind in (
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            ):
                continue

            if param.annotation in self._registration:
                new_args.append(self.get(param.annotation))
                continue

            if param.annotation != inspect.Parameter.empty:
                # has annotation
                if (
                    args_pos < args_length
                    and type(args[args_pos]) == param.annotation
                ):
                    new_args.append(args[args_pos])
                    args_pos += 1
                elif param.name in kwargs and type(
                    kwargs[param.name] == param.annotation
                ):
                    pass
                else:
                    raise ValueError(
                        f"Incorrect parameter provided for '{name}' in {implementation.__name__}"
                    )
            else:
                # no annotation
                if args_pos < args_length:
                    new_args.append(args[args_pos])
                    args_pos += 1
                elif param.name in kwargs:
                    pass
                else:
                    raise ValueError(
                        f"Incorrect parameter provided for '{name}' in {implementation.__name__}"
                    )

        return implementation(*new_args, **kwargs)
