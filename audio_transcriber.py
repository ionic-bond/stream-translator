import os
import queue
from scipy.io.wavfile import write as write_audio

import numpy as np
from openai import OpenAI

import filters
from common import TranslationTask, SAMPLE_RATE

TEMP_AUDIO_FILE_NAME = 'temp.wav'


def _filter_text(text: str, whisper_filters: str):
    filter_name_list = whisper_filters.split(',')
    for filter_name in filter_name_list:
        filter = getattr(filters, filter_name)
        if not filter:
            raise Exception('Unknown filter: %s' % filter_name)
        text = filter(text)
    return text


class OpenaiWhisper():

    def __init__(self, model: str) -> None:
        print("Loading whisper model: {}".format(model))
        import whisper
        self.model = whisper.load_model(model)

    def transcribe(self, audio: np.array, **transcribe_options) -> str:
        result = self.model.transcribe(audio, without_timestamps=True, **transcribe_options)
        return result.get("text")

    def work(self, input_queue: queue.SimpleQueue[TranslationTask],
             output_queue: queue.SimpleQueue[TranslationTask], whisper_filters,
             **transcribe_options):
        while True:
            task = input_queue.get()
            task.transcribed_text = _filter_text(self.transcribe(task.audio, **transcribe_options),
                                                 whisper_filters).strip()
            if not task.transcribed_text:
                print('skip...')
                continue
            print(task.transcribed_text)
            output_queue.put(task)


class FasterWhisper(OpenaiWhisper):

    def __init__(self, model: str) -> None:
        print("Loading faster-whisper model: {}".format(model))
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model)

    def transcribe(self, audio: np.array, **transcribe_options) -> str:
        segments, info = self.model.transcribe(audio, **transcribe_options)
        transcribed_text = ""
        for segment in segments:
            transcribed_text += segment.text
        return transcribed_text


class RemoteOpenaiWhisper(OpenaiWhisper):
    # https://platform.openai.com/docs/api-reference/audio/createTranscription?lang=python

    def __init__(self) -> None:
        self.client = OpenAI()

    def transcribe(self, audio: np.array, **transcribe_options) -> str:
        with open(TEMP_AUDIO_FILE_NAME, 'wb') as audio_file:
            write_audio(audio_file, SAMPLE_RATE, audio)
        with open(TEMP_AUDIO_FILE_NAME, 'rb') as audio_file:
            result = self.client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, language=transcribe_options['language']).text
        os.remove(TEMP_AUDIO_FILE_NAME)
        return result
