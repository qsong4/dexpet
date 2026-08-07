"""Emotion state machine tests."""

from backend.core.emotion import Emotion, EmotionStateMachine


def test_user_message_to_thinking():
    fsm = EmotionStateMachine()
    assert fsm.on_user_message() == Emotion.THINKING


def test_first_token_to_speaking():
    fsm = EmotionStateMachine()
    fsm.on_user_message()
    assert fsm.on_first_token() == Emotion.SPEAKING


def test_error_to_sad():
    fsm = EmotionStateMachine()
    assert fsm.on_error() == Emotion.SAD


def test_idle_timeout():
    fsm = EmotionStateMachine(idle_timeout_sec=10)
    fsm.apply_labeled_emotion(Emotion.HAPPY)
    assert fsm.state == Emotion.HAPPY
    # not yet
    assert fsm.on_idle_tick(fsm._last_active + 5) == Emotion.HAPPY
    assert fsm.on_idle_tick(fsm._last_active + 11) == Emotion.IDLE


def test_parse_emotion_tag():
    text, emo = EmotionStateMachine.parse_emotion_tag("你好呀 [[emotion:happy]]")
    assert text == "你好呀"
    assert emo == Emotion.HAPPY


def test_infer_from_keywords():
    fsm = EmotionStateMachine()
    assert fsm.infer_from_text("太好了，成功了") == Emotion.HAPPY
    assert fsm.infer_from_text("抱歉，失败了") == Emotion.SAD


def test_prompt_fragment():
    fsm = EmotionStateMachine()
    fsm.apply_labeled_emotion(Emotion.CURIOUS)
    assert "好奇" in fsm.prompt_fragment()
