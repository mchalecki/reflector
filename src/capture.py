import subprocess
import time
from threading import Thread
from queue import Queue, Empty
import io
import logging
from multiprocessing import Process, Queue as QueueMulti

from pydub import AudioSegment

FRAMERATE = 41000

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Capturer:
    def __init__(self, cmd):
        self.playing = True
        self.last_operation = time.time()
        self.cmd = cmd
        self.last_playing_update = None
        self.start_wave_nonblocking = None
        self.sound_interval = .6
        self.event_interval = .3

        self.queue = QueueMulti()

    def play_wave(self):
        producer = Process(target=self.produce)
        producer.start()
        consumer = Process(target=self.consume)
        consumer.start()

    def produce(self):
        ps = subprocess.Popen(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        q = Queue()
        t = Thread(target=self.enqueue_output, args=(ps.stdout, q))
        t.daemon = True
        t.start()

        last_playing_updated = time.time()
        temporal_playing = False
        self.start_wave_nonblocking = time.time()
        not_play_start = self.start_wave_nonblocking
        last_operation = time.time()
        buffer = bytearray()

        playing = False
        while True:
            try:
                line = q.get_nowait()
            except Empty:
                if temporal_playing:
                    not_play_start = time.time()
                    temporal_playing = False
            else:
                temporal_playing = True
                buffer += line

            if time.time() - last_playing_updated > self.sound_interval:  # update self.playing
                playing = self.get_playing(not_play_start, temporal_playing)
                last_playing_updated = time.time()

            if time.time() - last_operation > self.event_interval:
                last_operation = time.time()
                self.queue.put((buffer, playing))
                buffer = bytearray()

    def consume(self):
        start_time = time.time()
        current_value = 0
        counter = 0
        while time.time() - start_time < 10:
            loudness_over_time = []
            current, is_playing = self.queue.get()
            if current:
                iob = io.BytesIO(current)
                sound = AudioSegment.from_file(iob, format="raw", channels=1, sample_width=2, frame_rate=FRAMERATE)

                num_chunks = 1  # px
                chunk_size = int(len(sound) / num_chunks)
                if chunk_size > 0:
                    for i in range(0, len(sound), chunk_size):
                        chunk = sound[i:i + chunk_size]
                        try:
                            loudness_over_time.append(
                                chunk.rms)  # im not sure by what len(chunk) has to be divisible so there is double try
                        except Exception:
                            try:
                                loudness_over_time.append(chunk[:-1].rms)
                            except Exception:
                                print("Cannot calculate rms.")
                if loudness_over_time:
                    current_value = loudness_over_time[0]
                    counter += 1

            if not is_playing:
                current_value = 0

            logger.info(current_value)
        logger.info(counter)

    def get_playing(self, not_play_start, temporal_playing):
        this_time = time.time()
        if temporal_playing:
            return True
        elif this_time - self.start_wave_nonblocking < self.sound_interval:  # f.ex update every 1s this called after .5s
            return False if not_play_start == self.start_wave_nonblocking else True
        else:
            return False if this_time - not_play_start > self.sound_interval else True

    @staticmethod
    def enqueue_output(out, queue):
        for line in iter(out.readline, b''):
            queue.put(line)
        out.close()


def main():
    cmd = f"parec -d alsa_output.pci-0000_00_1b.0.analog-stereo.monitor --channels 1 --rate {FRAMERATE}"
    capturer = Capturer(cmd)
    capturer.play_wave()


if __name__ == '__main__':
    main()

    # wavef = wave.open('sound.wav', 'w')
    # wavef.setnchannels(1)
    # wavef.setsampwidth(2)
    # wavef.setframerate(FRAMERATE)
    # frame = np.frombuffer(buff, np.uint16)
    # wavef.writeframesraw(line)
