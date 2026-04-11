"""Tests for MongoDB query compiler — compiles F expressions to MongoDB query documents."""

import pytest

from ff_storage.query.expressions import AND, OR, F, FilterExpression
from ff_storage.query.mongo_compiler import compile_filter, compile_filters


class TestCompileFilterEquality:
    def test_equal(self):
        assert compile_filter(F.status == "active") == {"status": "active"}

    def test_equal_int(self):
        assert compile_filter(F.count == 42) == {"count": 42}

    def test_equal_none_is_null(self):
        assert compile_filter(F.deleted_at == None) == {"deleted_at": None}  # noqa: E711

    def test_not_equal(self):
        assert compile_filter(F.status != "deleted") == {"status": {"$ne": "deleted"}}

    def test_not_equal_none_is_not_null(self):
        assert compile_filter(F.field != None) == {"field": {"$ne": None}}  # noqa: E711


class TestCompileFilterComparison:
    def test_greater_than(self):
        assert compile_filter(F.price > 100) == {"price": {"$gt": 100}}

    def test_greater_equal(self):
        assert compile_filter(F.price >= 100) == {"price": {"$gte": 100}}

    def test_less_than(self):
        assert compile_filter(F.price < 50) == {"price": {"$lt": 50}}

    def test_less_equal(self):
        assert compile_filter(F.price <= 50) == {"price": {"$lte": 50}}


class TestCompileFilterNull:
    def test_is_null(self):
        assert compile_filter(F.field.is_null()) == {"field": None}

    def test_is_not_null(self):
        assert compile_filter(F.field.is_not_null()) == {"field": {"$ne": None}}


class TestCompileFilterIn:
    def test_in_list(self):
        assert compile_filter(F.status.in_(["a", "b", "c"])) == {"status": {"$in": ["a", "b", "c"]}}

    def test_not_in_list(self):
        assert compile_filter(F.status.not_in(["x", "y"])) == {"status": {"$nin": ["x", "y"]}}

    def test_in_empty_list(self):
        result = compile_filter(F.status.in_([]))
        assert result == {"_impossible": True}

    def test_not_in_empty_list(self):
        result = compile_filter(F.status.not_in([]))
        assert result == {}


class TestCompileFilterBetween:
    def test_between(self):
        result = compile_filter(F.age.between(18, 65))
        assert result == {"age": {"$gte": 18, "$lte": 65}}


class TestCompileFilterLike:
    def test_contains(self):
        result = compile_filter(F.name.contains("test"))
        assert result == {"name": {"$regex": "test"}}

    def test_startswith(self):
        result = compile_filter(F.name.startswith("ab"))
        assert result == {"name": {"$regex": "^ab"}}

    def test_endswith(self):
        result = compile_filter(F.name.endswith("cd"))
        assert result == {"name": {"$regex": "cd$"}}

    def test_icontains(self):
        result = compile_filter(F.name.icontains("TEST"))
        assert result == {"name": {"$regex": "TEST", "$options": "i"}}

    def test_contains_with_regex_metacharacters(self):
        result = compile_filter(F.name.contains("a.b"))
        assert result == {"name": {"$regex": r"a\.b"}}

    def test_contains_with_special_chars(self):
        result = compile_filter(F.name.contains("100%"))
        # The LIKE escape converts % to \%, then the regex converter handles it
        assert "$regex" in result["name"]


class TestCompileFilterComposite:
    def test_and(self):
        result = compile_filter(AND(F.a == 1, F.b == 2))
        assert result == {"$and": [{"a": 1}, {"b": 2}]}

    def test_or(self):
        result = compile_filter(OR(F.x == "a", F.x == "b"))
        assert result == {"$or": [{"x": "a"}, {"x": "b"}]}

    def test_nested_and_or(self):
        result = compile_filter(AND(F.price > 100, OR(F.status == "a", F.status == "b")))
        assert result == {
            "$and": [
                {"price": {"$gt": 100}},
                {"$or": [{"status": "a"}, {"status": "b"}]},
            ]
        }


class TestCompileFilters:
    def test_empty(self):
        assert compile_filters([]) == {}

    def test_single(self):
        result = compile_filters([F.status == "active"])
        assert result == {"status": "active"}

    def test_multiple(self):
        result = compile_filters([F.price > 100, F.status == "active"])
        assert result == {"$and": [{"price": {"$gt": 100}}, {"status": "active"}]}

    def test_three_filters(self):
        result = compile_filters([F.a == 1, F.b == 2, F.c == 3])
        assert result == {"$and": [{"a": 1}, {"b": 2}, {"c": 3}]}


class TestCompileFilterErrors:
    def test_invalid_type(self):
        with pytest.raises(TypeError):
            compile_filter("not an expression")

    def test_subquery_not_supported(self):
        expr = FilterExpression("field", "IN_SUBQUERY", "fake_subquery")
        with pytest.raises(NotImplementedError):
            compile_filter(expr)
