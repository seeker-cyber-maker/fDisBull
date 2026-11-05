; benchmark generated from python API
(set-info :status unknown)
(declare-fun x_1_4 () Bool)
(declare-fun x_1_2 () Bool)
(declare-fun x_1_5 () (_ BitVec 16))
(declare-fun x_1_3 () (_ BitVec 16))
(declare-fun x_1_1 () (_ BitVec 16))
(declare-fun x_1_0 () (_ BitVec 16))
(assert
 and)
(assert
 (let (($x90 (ite x_1_2 (ite x_1_4 true false) false)))
(let ((?x89 (ite x_1_2 (ite x_1_4 x_1_3 x_1_5) x_1_5)))
(let ((?x71 (bvsub x_1_0 x_1_1)))
(let ((?x88 (ite x_1_2 (ite x_1_4 (bvsub ?x71 x_1_3) (bvsub ?x71 x_1_3)) ?x71)))
(or (and (distinct ?x88 ?x88) true) (and (distinct ?x89 ?x89) true) (and (distinct $x90 $x90) true)))))))
(check-sat)
