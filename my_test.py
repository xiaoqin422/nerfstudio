from typing import Any


class Person:
    name: str
    value: Any

    def __init__(self, name: str, value: any):
        self.name = name
        self.value = value

    def redundancy_key(self) -> str:
        return f"{type(self).__name__}_{self.name}"


class Student(Person):

    def redundancy_key(self) -> str:
        return f"{type(self).__name__}_{self.name}"


if __name__ == '__main__':
    s = Student(name="笑笑", value=1)
    print(s.redundancy_key())
