from functools import total_ordering
from typing import Iterable, List, Optional, Set, Tuple, Union


class ExecuteTest:
    """
    ExecuteTest defines the set of tests that should be run together from a single test file.
    """

    test_file: str
    _exclued: Set[str]  # Tests that should be excluded from this test run
    _included: Set[str]  # If non-empy, only these tests should be run in this test run

    def __init__(
        self,
        name: str,
        excluded: Optional[Iterable[str]] = None,
        included: Optional[Iterable[str]] = None,
    ) -> None:
        self._excluded = set()
        self._included = set()

        if excluded and included:
            raise ValueError("Can't specify both included and excluded")

        if "::" in name:
            assert (
                not included and not excluded
            ), "Can't specify included or excluded tests when specifying a test class in the file name"
            self.test_file, test_class = name.split("::")
            self._included.add(test_class)
        else:
            self.test_file = name

        # For testing purposes
        if excluded:
            self._excluded = set(excluded)
        if included:
            self._included = set(included)

    def __bool__(self) -> bool:
        return not self.is_empty()

    @staticmethod
    def empty() -> "ExecuteTest":
        return ExecuteTest("")

    def is_empty(self) -> bool:
        # Lack of a test_file means that this is an empty run,
        # which means there is nothing to run. It's the zero.
        return not self.test_file

    def __repr__(self) -> str:
        r: str = f"RunTest({self.test_file}"
        r += f", included: {self._included}" if self._included else ""
        r += f", excluded: {self._excluded}" if self._excluded else ""
        r += ")"
        return r

    def __str__(self) -> str:
        if self.is_empty():
            return "Empty"

        pytest_filter = self.get_pytest_filter()
        if pytest_filter:
            return self.test_file + ", " + pytest_filter
        return self.test_file

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExecuteTest):
            return False

        ret = self.test_file == other.test_file
        ret = ret and self._included == other._included
        ret = ret and self._excluded == other._excluded
        return ret

    def _is_full_file(self) -> bool:
        return not self._included and not self._excluded

    def __or__(self, other: "ExecuteTest") -> "ExecuteTest":
        """
        To OR/Union test runs means to run all the tests that either of the two runs specify.
        """

        # Is any file empty?
        if self.is_empty():
            return other
        if other.is_empty():
            return self

        # If not, ensure we have the same file
        assert (
            self.test_file == other.test_file
        ), f"Can't exclude {other} from {self} because they're not the same test file"

        # 4 possible cases:

        # 1. Either file is the full file, so union is everything
        if self._is_full_file() or other._is_full_file():
            # The union is the whole file
            return ExecuteTest(self.test_file)

        # 2. Both files only run what's in _included, so union is the union of the two sets
        if self._included and other._included:
            return ExecuteTest(
                self.test_file, included=self._included.union(other._included)
            )

        # 3. Both files only exclude what's in _excluded, so union is the intersection of the two sets
        if self._excluded and other._excluded:
            return ExecuteTest(
                self.test_file, excluded=self._excluded.intersection(other._excluded)
            )

        # 4. One file includes and the other excludes, so we then continue excluding the _excluded set minus
        #    whatever is in the _included set
        included = self._included | other._included
        excluded = self._excluded | other._excluded
        return ExecuteTest(self.test_file, excluded=excluded - included)

    def __ior__(
        self, other: "ExecuteTest"
    ) -> "ExecuteTest":  # noqa: PYI034 Method returns `self`
        res = self | other
        self.test_file = res.test_file
        self._included = res._included
        self._excluded = res._excluded

        return self

    def __sub__(self, other: "ExecuteTest") -> "ExecuteTest":
        """
        To subtract test runs means to run all the tests in the first run except for what the second run specifies.

        It is currently an error if the subtraction will result in no tests being run.
        """

        # Is any file empty?
        if self.is_empty():
            return ExecuteTest.empty()
        if other.is_empty():
            return self

        assert (
            self.test_file == other.test_file
        ), f"Can't exclude {other} from {self} because they're not the same test file"

        if other._is_full_file():
            return ExecuteTest.empty()

        def return_inclusions_or_empty(inclusions: Set[str]) -> ExecuteTest:
            if inclusions:
                return ExecuteTest(self.test_file, included=inclusions)
            return ExecuteTest.empty()

        if other._included:
            if self._included:
                return return_inclusions_or_empty(self._included - other._included)
            else:
                return ExecuteTest(
                    self.test_file, excluded=self._excluded | other._included
                )
        else:
            if self._included:
                return return_inclusions_or_empty(self._included & other._excluded)
            else:
                return return_inclusions_or_empty(other._excluded - self._excluded)

    def __isub__(
        self, other: "ExecuteTest"
    ) -> "ExecuteTest":  # noqa: PYI034  Method returns `self`
        res = self - other
        self.test_file = res.test_file
        self._included = res._included
        self._excluded = res._excluded
        return self

    def __and__(self, other: "ExecuteTest") -> "ExecuteTest":
        return (self | other) - (self - other) - (other - self)

    def get_pytest_filter(self) -> str:
        if self._included:
            return " or ".join(sorted(self._included))
        elif self._excluded:
            return f"not ({' and '.join(sorted(self._excluded))})"
        else:
            return ""

    def contains(self, test: "ExecuteTest") -> bool:
        if self.test_file != test.test_file:
            return False

        if not self._included and not self._excluded:
            return True  # self contains all tests

        if not test._included and not test._excluded:
            return False  # test contains all tests, but self doesn't

        # Does self exclude a subset of what test excldes?
        if test._excluded:
            return test._excluded.issubset(self._excluded)

        # Does self include everything test includes?
        if self._included:
            return test._included.issubset(self._included)

        # Getting to here means that test includes and self excludes
        # Does self exclude anything test includes? If not, we're good
        return not self._excluded.intersection(test._included)


TestRuns = Tuple[ExecuteTest, ...]


@total_ordering
class ShardedTest:
    test: ExecuteTest
    shard: int
    num_shards: int
    time: Optional[float]  # In seconds

    def __init__(
        self,
        test: Union[ExecuteTest, str],
        shard: int,
        num_shards: int,
        time: Optional[float] = None,
    ) -> None:
        if isinstance(test, str):
            test = ExecuteTest(test)
        self.test = test
        self.shard = shard
        self.num_shards = num_shards
        self.time = time

    @property
    def name(self) -> str:
        return self.test.test_file

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShardedTest):
            return False
        return (
            self.name == other.name
            and self.shard == other.shard
            and self.num_shards == other.num_shards
            and self.time == other.time
        )

    def __repr__(self) -> str:
        ret = f"{self.test} {self.shard}/{self.num_shards}"
        if self.time:
            ret += f" ({self.time}s)"

        return ret

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ShardedTest):
            raise NotImplementedError

        # This is how the list was implicity sorted when it was a NamedTuple
        if self.name != other.name:
            return self.name < other.name
        if self.shard != other.shard:
            return self.shard < other.shard
        if self.num_shards != other.num_shards:
            return self.num_shards < other.num_shards

        # None is the smallest value
        if self.time is None:
            return True
        if other.time is None:
            return False
        return self.time < other.time

    def __str__(self) -> str:
        return f"{self.name} {self.shard}/{self.num_shards}"

    def get_time(self) -> float:
        return self.time or 0

    def get_pytest_args(self) -> List[str]:
        return ["-k", self.test.get_pytest_filter()]
