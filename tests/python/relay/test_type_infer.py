"""Test that type checker correcly computes types
   for expressions.
"""
import tvm
import numpy as np
from tvm.relay.ir_pass import check_expr
from tvm.relay.ir_builder import IRBuilder, func_type
from tvm.relay.ir_builder import scalar_type, convert, tensor_type
from tvm.relay.env import Environment
from tvm.relay.op import log, add, equal, subtract, concat
from tvm.relay.expr import Function

def assert_has_type(expr, typ, env=Environment({})):
    checked_expr = check_expr(env, expr)
    assert checked_expr.checked_type() == typ


def assert_decl_has_type(env, name, typ):
    func = env[name]
    assert func.checked_type() == typ


def test_monomorphic_let():
    "Program: let x = 1; return x"
    b = IRBuilder()
    x = b.let('x', 1.0, value_type=scalar_type('float64'))
    b.ret(x)

    prog, env = b.get()
    assert_has_type(prog, scalar_type('float64'))


def test_single_op():
    "Program: fn (x : float32) { let t1 = f(x); t1 }"
    b = IRBuilder()
    with b.function(('x', 'float32')) as func:
        x, = func.param_ids()
        t1 = b.let('t1', log(x))
        b.ret(t1)
    assert_has_type(func.to_func(), func_type(['float32'], 'float32'))

def test_add_op():
    """
    Program:
        fn (x, y) {
            return x + y;
        }
    """
    b = IRBuilder()
    x = b.param('x', tensor_type(5, 5, 5))
    y = b.param('y', tensor_type(5, 5, 5))
    with b.function(x, y) as func:
        b.ret(add(x.var, y.var))
    b.ret(func)
    prog, env = b.get()
    ttype = tensor_type(5, 5, 5)
    expected_ty = func_type([ttype, ttype], ttype)
    assert_has_type(func.to_func(), expected_ty)

def test_add_broadcast_op():
    """
    Program:
        fn (x: Tensor[(10, 4), f32], y: Tensor[(5, 10, 1), f32]) -> Tensor[(5, 10, 4), f32] {
            return x + y;
        }
    """
    b = IRBuilder()
    x = b.param('x', tensor_type(10, 4))
    y = b.param('y', tensor_type(5, 10, 1))
    with b.function(x, y) as func:
        b.ret(add(x.var, y.var))
    b.ret(func)
    prog, env = b.get()
    ttype = tensor_type(5, 5, 5)
    expected_ty = func_type([ttype, ttype], ttype)
    assert_has_type(func.to_func(), expected_ty)

def test_dual_op():
    """Program:
       fn (x : Tensor[f32, (10, 10)]) {
         let t1 = log(x);
         let t2 = add(t1, x);
         return t1;
       }
    """
    b = IRBuilder()
    with b.function(('x', tensor_type(10, 10))) as func:
        x, = func.param_ids()
        t1 = b.let('t1', log(x))
        t2 = b.let('t2', add(t1, x))
        b.ret(t2)
    assert_has_type(func.to_func(), func_type(['float32'], 'float32'))


def test_decl():
    """Program:
       def f(x : Tensor[f32, (10, 10)]) {
           let lx = log(x);
           return lx;
       }
    """
    b = IRBuilder()
    x = b.param('x')
    with b.decl('f', x):
        lx = b.let('lx', log(x))
        b.ret(lx)
    _, env = b.get()
    assert_decl_has_type(env, 'f', func_type(['float32'], 'float32'))


def test_recursion():
    """
    Program:
       def f(n: i32, data: f32) -> f32 {
          if (n == 0) {
              return f(n - 1, log(data));
          } else {
              return data;
          }
       }
       f(2, 10000);
    """
    b = IRBuilder()
    f = b.global_var('f')
    n = b.param('n', ty='int32')
    data = b.param('data', ty='float32')
    with b.decl(f, n, data):
        with b.if_scope(equal(n, convert(0))):
            b.ret(f(subtract(n, convert(1)), log(data)))
        with b.else_scope():
            b.ret(data)
    b.ret(f(convert(2.0), convert(10000.0)))
    assert_decl_has_type(b.env, 'f', func_type(
        ['int32', 'float32'], 'float32'))
    # TODO(@jroesch): need evaluator or new runtime
    # to execute this.

def test_concat():
    """
    Program:
        def try_concat2(x: Float(3, 2), y: Float(2, 2)) -> Float(5, 2) {
            return concat(x, y);
        }
    """
    ib = IRBuilder()
    try_concat2 = ib.global_var('try_concat2')
    x = ib.param('x', ty=tensor_type(3, 2))
    y = ib.param('y', ty=tensor_type(2, 2))
    with ib.decl(try_concat2, x, y):
        ib.ret(concat(x, y))
    fn_ty = func_type([tensor_type(3, 2), tensor_type(2, 2)], tensor_type(5, 2))
    assert_decl_has_type(ib.env, try_concat2, fn_ty)

if __name__ == "__main__":
    test_recursion()

    test_monomorphic_let()
    test_single_op()
    test_add_op()
    test_add_broadcast_op()
    test_dual_op()
    test_decl()
    test_concat()
