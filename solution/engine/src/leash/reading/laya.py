"""Shared Laya response validation and full-context checks for training and inference."""

import math


def decode(answers, questions):
    if set(answers) != set(questions):
        raise ValueError('model returned different questions')
    predictions = {}
    for qid, question in questions.items():
        answer = answers[qid]
        if answer['type'] != question['type']:
            raise ValueError('model returned different question type')
        if question['type'] == 'noul':
            p = answer['noul']
            if type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError('invalid model probability')
            predictions[qid] = p > .5  # false wins the canonical [false, true] tie.
        else:
            probabilities = answer['probabilities']
            if (set(probabilities) != set(question['criteria']) or
                    any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
                        for p in probabilities.values()) or
                    not math.isclose(sum(probabilities.values()), 1, abs_tol=.001) or
                    answer['choice'] not in probabilities):
                raise ValueError('invalid model choice/probabilities')
            # The runtime's choice precedes rounding of its displayed probabilities.
            predictions[qid] = answer['choice']
    return predictions


def sequence_fits(agent, state, questions):
    """Compare the actual input to an untruncated rendering, including options."""
    from laya.common import build_sequence, render_options, serialize_state  # type: ignore[import-not-found]
    tok = agent.tok
    state_ids = tok(serialize_state(state).replace(tok.mask_token, ' '), add_special_tokens=False)['input_ids']
    for qid, spec in questions.items():
        q = agent._to_internal(spec)
        if any(len(tok(' ' + option.replace(tok.mask_token, ' '), add_special_tokens=False)['input_ids']) > 48
               for option in render_options(q)):
            return f'{qid}: option_would_truncate'
        full = build_sequence(tok, state, q, 1_000_000, 1_000_000, state_ids=state_ids)
        bounded = build_sequence(tok, state, q, agent.cfg['max_len'], agent.cfg['head_max_len'], state_ids=state_ids)
        if bounded != full:
            return f'{qid}: input_would_truncate'
    return None

