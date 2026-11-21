/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef AGI_DECODE_H
#define AGI_DECODE_H

#include <stdbool.h>
#include <stdint.h>

#define AGI_CODE_MAX 65536
#define AGI_INSN_MAX 64
#define AGI_DECODE_OPERANDS_MAX 3
#define AGI_DECODE_PREDICATES_MAX 8
#define AGI_DECODE_TOKENS_MAX AGI_INSN_MAX

typedef enum AgiFault {
    AGI_FAULT_NONE,
    AGI_FAULT_OPCODE,
    AGI_FAULT_TRUNCATED,
    AGI_FAULT_ACTOR,
    AGI_FAULT_BRANCH,
    AGI_FAULT_CONDITION,
    AGI_FAULT_FETCH,
    AGI_FAULT_CONDITION_LIMIT,
    AGI_FAULT_MISSING_VIEW,
    AGI_FAULT_VIEW_NOT_LOADED,
    AGI_FAULT_VIEW_UNBOUND,
    AGI_FAULT_LOOP,
    AGI_FAULT_CEL,
    AGI_FAULT_EMPTY_LOOP
} AgiFault;

typedef enum AgiDecodeProfile {
    AGI_DECODE_SCALAR, AGI_DECODE_BINDING, AGI_DECODE_INTENT
} AgiDecodeProfile;

typedef enum AgiExecutionSupport {
    AGI_EXEC_NATIVE, AGI_EXEC_PENDING_HOST, AGI_EXEC_UNSUPPORTED_PROFILE
} AgiExecutionSupport;

typedef enum AgiOperandKind {
    AGI_OPERAND_VARIABLE, AGI_OPERAND_FLAG, AGI_OPERAND_ACTOR,
    AGI_OPERAND_VIEW, AGI_OPERAND_LOOP, AGI_OPERAND_CEL,
    AGI_OPERAND_U8, AGI_OPERAND_U16, AGI_OPERAND_S16
} AgiOperandKind;

typedef enum AgiOperandAccess {
    AGI_ACCESS_READ, AGI_ACCESS_WRITE, AGI_ACCESS_READ_WRITE,
    AGI_ACCESS_REFERENCE
} AgiOperandAccess;

typedef enum AgiEffectClass {
    AGI_EFFECT_SCALAR, AGI_EFFECT_FLAG, AGI_EFFECT_CONTROL,
    AGI_EFFECT_RESOURCE, AGI_EFFECT_ACTOR, AGI_EFFECT_HOST
} AgiEffectClass;

typedef enum AgiConditionKind {
    AGI_CONDITION_PREDICATE, AGI_CONDITION_OR_BEGIN,
    AGI_CONDITION_OR_END, AGI_CONDITION_NOT
} AgiConditionKind;

typedef enum AgiSuccessorKind {
    AGI_SUCCESSOR_FALLTHROUGH, AGI_SUCCESSOR_BRANCH,
    AGI_SUCCESSOR_TRUE, AGI_SUCCESSOR_FALSE
} AgiSuccessorKind;

typedef struct AgiDecodedOperand {
    const char *role;
    AgiOperandKind kind;
    AgiOperandAccess access;
    uint32_t width;
    /* An index for variable/flag kinds, otherwise the literal value. */
    int32_t value;
} AgiDecodedOperand;

typedef struct AgiDecodedCondition {
    AgiConditionKind kind;
    uint32_t pc, opcode, operand_count;
    const char *mnemonic;
    AgiDecodedOperand operands[2];
} AgiDecodedCondition;

typedef struct AgiDecodedSuccessor {
    AgiSuccessorKind kind;
    int64_t pc;
    bool in_range;
} AgiDecodedSuccessor;

typedef struct AgiDecodedInstruction {
    uint32_t pc, opcode, size;
    uint8_t bytes[AGI_INSN_MAX];
    const char *mnemonic, *operation;
    AgiEffectClass effect_class;
    AgiExecutionSupport execution_support;
    AgiFault fault;
    uint32_t operand_count, condition_count, successor_count;
    AgiDecodedOperand operands[AGI_DECODE_OPERANDS_MAX];
    AgiDecodedCondition conditions[AGI_DECODE_TOKENS_MAX];
    AgiDecodedSuccessor successors[2];
} AgiDecodedInstruction;

/* The caller supplies immutable code and a nonnull output. The reader is only
 * called at admitted byte offsets. TCG uses its tracked instruction fetch;
 * stopped inspection uses the machine's immutable copy. No guest state is read.
 *
 * Structural decoding is independent of execution_support. On a fault, size
 * remains zero and no complete extent/successor is claimed. In particular,
 * known commands can be structurally decoded in a profile that cannot run them.
 */
typedef uint8_t (*AgiDecodeRead)(void *opaque, uint32_t pc);
bool agi_decode(AgiDecodeRead read, void *opaque, uint32_t code_size,
                uint32_t pc, AgiDecodeProfile profile,
                AgiDecodedInstruction *out);

const char *agi_operand_kind_name(AgiOperandKind kind);
const char *agi_operand_access_name(AgiOperandAccess access);
const char *agi_condition_kind_name(AgiConditionKind kind);
const char *agi_successor_kind_name(AgiSuccessorKind kind);
const char *agi_effect_class_name(AgiEffectClass effect);
const char *agi_execution_support_name(AgiExecutionSupport support);

#endif
