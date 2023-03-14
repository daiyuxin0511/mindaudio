"""
Eval DeepSpeech2
"""
import argparse
import json
import pickle
import numpy as np
import os
from mindspore import context
from mindspore.train.serialization import load_checkpoint, load_param_into_net

from mindaudio.models.deepspeech2 import DeepSpeechModel
from mindaudio.models.decoders.greedydecoder import MSGreedyDecoder
from hparams.hparams import parse_args
from dataset import create_base_dataset, eval_data_pipeline


class PredictWithSoftmax(nn.Cell):
    """
    PredictWithSoftmax
    """

    def __init__(self, network):
        super(PredictWithSoftmax, self).__init__(auto_prefix=False)
        self.network = network
        self.inference_softmax = P.Softmax(axis=-1)
        self.transpose_op = P.Transpose()
        self.cast_op = P.Cast()

    def construct(self, inputs, input_length):
        x, output_sizes = self.network(inputs, self.cast_op(input_length, mstype.int32))
        x = self.inference_softmax(x)
        x = self.transpose_op(x, (1, 0, 2))
        return x, output_sizes


if __name__ == '__main__':
    args = parse_args()
    context.set_context(device_id=args.device_id,mode=context.GRAPH_MODE,
                        device_target=args.device_target, save_graphs=False)

    labels = args.labels

    model = PredictWithSoftmax(DeepSpeechModel(batch_size=args.EvalDataConfig.batch_size,
                                               rnn_hidden_size=args.ModelConfig.hidden_size,
                                               nb_layers=args.ModelConfig.hidden_layers,
                                               labels=labels,
                                               rnn_type=args.ModelConfig.rnn_type,
                                               audio_conf=args.DataConfig.SpectConfig,
                                               bidirectional=args.bidirectional))

    ds_eval = create_base_dataset(manifest_filepath=args.EvalDataConfig.test_manifest,
                                   labels=args.labels, rank=rank_id, group_size=group_size)
    ds_eval = eval_data_pipeline(ds_eval, batch_size=args.EvalDataConfig.batch_size,
                                   audio_conf=args.DataConfig.SpectConfig)

    param_dict = load_checkpoint(args.pretrain_ckpt)
    load_param_into_net(model, param_dict)
    # load_param_into_net(model, param_dict)
    print('Successfully loading the pre-trained model')

    if args.LMConfig.decoder_type == 'greedy':
        decoder = MSGreedyDecoder(labels=labels, blank_index=labels.index('_'))
    else:
        raise NotImplementedError("Only greedy decoder is supported now")
    target_decoder = MSGreedyDecoder(labels, blank_index=labels.index('_'))

    model.set_train(False)
    total_cer, total_wer, num_tokens, num_chars = 0, 0, 0, 0
    output_data = []
    for data in ds_eval.create_dict_iterator():
        inputs, input_length, target_indices, targets = data['inputs'], data['input_length'], data['target_indices'], \
            data['label_values']

        split_targets = []
        start, count, last_id = 0, 0, 0
        target_indices, targets = target_indices.asnumpy(), targets.asnumpy()
        for i in range(np.shape(targets)[0]):
            if target_indices[i, 0] == last_id:
                count += 1
            else:
                split_targets.append(list(targets[start:count]))
                last_id += 1
                start = count
                count += 1
        split_targets.append(list(targets[start:]))
        out, output_sizes = model(inputs, input_length)
        decoded_output, _ = decoder.decode(out, output_sizes)
        target_strings = target_decoder.convert_to_strings(split_targets)

        if args.save_output is not None:
            output_data.append((out.asnumpy(), output_sizes.asnumpy(), target_strings))
        for doutput, toutput in zip(decoded_output, target_strings):
            transcript, reference = doutput[0], toutput[0]
            wer_inst = decoder.wer(transcript, reference)
            cer_inst = decoder.cer(transcript, reference)
            total_wer += wer_inst
            total_cer += cer_inst
            num_tokens += len(reference.split())
            num_chars += len(reference.replace(' ', ''))
            if args.verbose:
                print("Ref:", reference.lower())
                print("Hyp:", transcript.lower())
                print("WER:", float(wer_inst) / len(reference.split()),
                      "CER:", float(cer_inst) / len(reference.replace(' ', '')), "\n")
    wer = float(total_wer) / num_tokens
    cer = float(total_cer) / num_chars

    print('Test Summary \t'
          'Average WER {wer:.3f}\t'
          'Average CER {cer:.3f}\t'.format(wer=wer * 100, cer=cer * 100))