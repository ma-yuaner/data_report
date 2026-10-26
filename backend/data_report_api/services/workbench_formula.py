"""Compile a small expression language. Never eval Python or accept raw SQL."""
import ast
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


def decimal_scale(value=6):
    if type(value) is not int or not 0 <= value <= 12:
        raise ValueError("小数位必须为0至12的整数")
    return value


def install_division(con, scale):
    def divide(a, b):
        if a is None or b is None or b == 0:
            return None
        with localcontext() as ctx:
            ctx.prec = 100
            return (a / b).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
    con.create_function(f"wb_formula_divide_{scale}", divide,
                        parameters=["DECIMAL(38,12)", "DECIMAL(38,12)"],
                        return_type=f"DECIMAL(38,{scale})", null_handling="special")


def compile_formula(text, fields, quote, scale=6):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError("请填写不超过2000字符的计算表达式")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, RecursionError):
        raise ValueError("计算表达式格式无效") from None
    if len(list(ast.walk(tree))) > 120:
        raise ValueError("计算表达式过于复杂，请拆成多个计算列")
    used, zero_checks = set(), []

    def number(result):
        sql, kind = result
        if kind not in ("decimal", "integer"):
            raise ValueError("参与计算的字段必须先转换为精确数值")
        return sql

    def string(result):
        if result[1] != "text":
            raise ValueError("文本函数需要文本字段或带引号的文字")
        return result[0]

    def integer(node, minimum=0):
        if not isinstance(node, ast.Constant) or type(node.value) is not int or not minimum <= node.value <= 100000:
            raise ValueError("函数位置、长度或小数位需要有效的整数常量")
        return node.value

    def field(node):
        if not isinstance(node, ast.Name) or node.id not in fields:
            raise ValueError("请从当前字段列表选择字段，字段标识不存在")
        used.add(node.id)
        return quote(node.id), fields[node.id]["type"]

    def visit(node):
        if isinstance(node, ast.Name):
            return field(node)
        if isinstance(node, ast.Constant):
            if type(node.value) is str:
                return "'" + node.value.replace("'", "''") + "'", "text"
            if type(node.value) in (int, float):
                raw = ast.get_source_segment(text, node)
                try:
                    value = Decimal(raw)
                    if not value.is_finite() or abs(value) >= Decimal("1e26") or value.as_tuple().exponent < -12:
                        raise InvalidOperation
                except (InvalidOperation, TypeError):
                    raise ValueError("数值常量最多26位整数、12位小数") from None
                return "CAST('" + format(value, "f") + "' AS DECIMAL(38,12))", "decimal"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = number(visit(node.operand))
            return f"({'-' if isinstance(node.op, ast.USub) else '+'}{value})", "decimal"
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = number(visit(node.left)), number(visit(node.right))
            if isinstance(node.op, ast.Div):
                zero_checks.append(f"({b})=0")
                return f"wb_formula_divide_{scale}({a},{b})", "decimal"
            symbol = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(node.op)]
            return f"CAST(({a} {symbol} {b}) AS DECIMAL(38,{scale}))", "decimal"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name, args = node.func.id, node.args
            if name in ("group_sum", "group_count"):
                if name == "group_sum" and not args:
                    raise ValueError("group_sum需要数值字段及可选分组字段")
                value = number(field(args[0])) if name == "group_sum" else "*"
                keys = args[1:] if name == "group_sum" else args
                partition = "PARTITION BY " + ",".join(field(k)[0] for k in keys) if keys else ""
                function = "SUM" if name == "group_sum" else "COUNT"
                return f"CAST({function}({value}) OVER ({partition}) AS DECIMAL(38,{scale}))", "decimal"
            if name == "abs" and len(args) == 1:
                return f"ABS({number(visit(args[0]))})", "decimal"
            if name == "round" and len(args) == 2:
                digits = integer(args[1])
                decimal_scale(digits)
                return f"ROUND({number(visit(args[0]))},{digits})", "decimal"
            if name == "coalesce" and 2 <= len(args) <= 8:
                values = [visit(arg) for arg in args]
                kinds = {v[1] for v in values}
                if len(kinds - {"integer", "decimal"}) and len(kinds) != 1:
                    raise ValueError("空值替换的字段和值必须为相同类型")
                return "COALESCE(" + ",".join(v[0] for v in values) + ")", values[0][1]
            if name == "concat" and 2 <= len(args) <= 20:
                # || preserves NULL; unlike SQL CONCAT it does not silently skip it.
                return "(" + " || ".join("CAST(" + visit(a)[0] + " AS VARCHAR)" for a in args) + ")", "text"
            if name == "trim" and len(args) == 1:
                return f"TRIM({string(visit(args[0]))})", "text"
            if name == "replace" and len(args) == 3:
                return "REPLACE(" + ",".join(string(visit(a)) for a in args) + ")", "text"
            if name == "substr" and len(args) == 3:
                return f"SUBSTR({string(visit(args[0]))},{integer(args[1], 1)},{integer(args[2])})", "text"
            if name == "days_between" and len(args) == 2:
                values = [visit(a) for a in args]
                if any(v[1] != "date" for v in values):
                    raise ValueError("日期差计算前请把两列转换为日期")
                return f"CAST(DATE_DIFF('day',{values[0][0]},{values[1][0]}) AS DECIMAL(38,{scale}))", "decimal"
        raise ValueError("表达式仅支持字段、常量、加减乘除括号和列出的受控函数")

    sql, kind = visit(tree.body)
    if kind in ("integer", "decimal"):
        sql = f"CAST({sql} AS DECIMAL(38,{scale}))"
        kind = "decimal"
    return sql, kind, used, zero_checks
