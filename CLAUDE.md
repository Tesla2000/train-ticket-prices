Always use pydantic BaseModel instead of dict as a type returned from a method or parameter type unless there is no other way to represent the data and approved by the user.

Project needs to be class focuses with no functions unless explicitly allowed by the user.

All used classes, except Protocols must be pydantic BaseModel subclasses unless explicitly allowed by the user. With arbitrary types not allowed and NON PYDANTIC and only non-pydantic classes, like coming from third party packages marked with InstanceOf[NonPydanticClass] for compliance.
