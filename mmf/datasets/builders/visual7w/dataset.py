# Copyright (c) Facebook, Inc. and its affiliates.

import torch
import numpy as np

from mmf.common.sample import Sample
from mmf.datasets.mmf_dataset import MMFDataset


class Visual7WDataset(MMFDataset):
    def __init__(self, config, *args, dataset_name="visual7w", **kwargs):
        super().__init__(dataset_name, config, *args, **kwargs)


    def iou(self, anchors, gt_boxes):
        """
        anchors: (N, 4) ndarray of float
        gt_boxes: (K, 4) ndarray of float
        overlaps: (N, K) ndarray of overlap between boxes and query_boxes
        """
        N = anchors.size(0)
        K = gt_boxes.size(0)

        gt_boxes_area = (
            (gt_boxes[:, 2] - gt_boxes[:, 0] + 1) * (gt_boxes[:, 3] - gt_boxes[:, 1] + 1)
        ).view(1, K)

        anchors_area = (
            (anchors[:, 2] - anchors[:, 0] + 1) * (anchors[:, 3] - anchors[:, 1] + 1)
        ).view(N, 1)

        boxes = anchors.view(N, 1, 4).expand(N, K, 4)
        query_boxes = gt_boxes.view(1, K, 4).expand(N, K, 4)

        iw = (
            torch.min(boxes[:, :, 2], query_boxes[:, :, 2])
            - torch.max(boxes[:, :, 0], query_boxes[:, :, 0])
            + 1
        )
        iw[iw < 0] = 0

        ih = (
            torch.min(boxes[:, :, 3], query_boxes[:, :, 3])
            - torch.max(boxes[:, :, 1], query_boxes[:, :, 1])
            + 1
        )
        ih[ih < 0] = 0

        ua = anchors_area + gt_boxes_area - (iw * ih)
        overlaps = iw * ih / ua

        return overlaps

    def __getitem__(self, idx):

        sample_info = self.annotation_db[idx]
        features_data = self.features_db[idx]
        multiple_choice_idx = torch.from_numpy(np.array(sample_info["mc_idx"]))

        boxes = features_data['image_info_0']['bbox']
        gt_boxes = \
            features_data['image_info_1']['bbox'][multiple_choice_idx, :]
        features = features_data['image_feature_0']
        gt_features = \
            features_data['image_feature_1'][multiple_choice_idx, :]

        mix_boxes = np.concatenate((boxes, gt_boxes), axis=0)
        mix_features = torch.tensor(np.concatenate((features, gt_features), axis=0))
        mix_max_features = features_data['image_info_0']['max_features'] \
            + features_data['image_info_1']['max_features']

        text_processor_argument = {"text": sample_info["caption"]}
        processed_question = self.text_processor(text_processor_argument)

        ref_box = sample_info["refBox"]

        # given the mix boxes, and ref_box, calculate the overlap.
        targets = self.iou(
            torch.tensor(gt_boxes[:, :4]).float(), torch.tensor([ref_box]).float()
        ).numpy()
        targets[targets < 0.5] = 0

        targets = np.argmax(targets)

        current_sample = Sample()
        current_sample.image_feature_0 = mix_features
        current_sample.input_ids = processed_question["input_ids"]
        current_sample.input_mask = processed_question["input_mask"]
        current_sample.segment_ids = processed_question["segment_ids"]
        current_sample.image_info_0 = {}
        current_sample.image_info_0["image_width"] = \
            features_data['image_info_0']['image_width']
        current_sample.image_info_0["image_height"] = \
            features_data['image_info_0']['image_height']
        current_sample.image_info_0['bbox'] = mix_boxes
        current_sample.image_info_0['max_features'] = mix_max_features
        current_sample.targets = torch.tensor([targets], dtype=torch.long)
        #current_sample.image_labels = torch.tensor([[0]])
        return current_sample
