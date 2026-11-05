; benchmark generated from python API
(set-info :status unknown)
(declare-fun x_3_2 () (_ BitVec 16))
(declare-fun x_3_1 () (_ BitVec 16))
(declare-fun x_3_0 () (_ BitVec 16))
(assert
 and)
(assert
 (let ((?x76 (bvadd x_3_0 x_3_1)))
(let (($x81 (bvsgt ?x76 x_3_2)))
(or (and (distinct $x81 $x81) true)))))
(check-sat)
