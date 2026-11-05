; benchmark generated from python API
(set-info :status unknown)
(declare-fun x_4_1 () (_ BitVec 16))
(declare-fun x_4_2 () (_ BitVec 8))
(declare-fun x_4_0 () (_ BitVec 8))
(assert
 (let (($x28 (bvult x_4_1 (_ bv32 16))))
 (and $x28 $x28)))
(assert
 (let ((?x66 (ite (and (distinct (_ bv0 16) (bvand x_4_1 (_ bv1 16))) true) (bvlshr x_4_2 (_ bv4 8)) x_4_2)))
(let ((?x6 (ite (bvsgt ((_ sign_extend 8) x_4_0) x_4_1) (bvand ?x66 (_ bv15 8)) (_ bv0 8))))
(or (and (distinct ?x6 ?x6) true)))))
(check-sat)
