; benchmark generated from python API
(set-info :status unknown)
(declare-fun x_2_0 () (_ BitVec 8))
(assert
 and)
(assert
 (let (($x23 (and (distinct (_ bv0 8) x_2_0) true)))
(let ((?x28 (ite $x23 (bvadd (_ bv100 16) (bvmul ((_ zero_extend 8) x_2_0) (_ bv100 16))) (_ bv100 16))))
(let ((?x24 (ite $x23 (bvmul (bvadd ((_ zero_extend 8) x_2_0) (_ bv1 16)) (_ bv100 16)) (_ bv100 16))))
(or (and (distinct ?x24 ?x28) true))))))
(check-sat)
