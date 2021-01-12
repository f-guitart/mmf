# Copyright (c) Facebook, Inc. and its affiliates.

import logging
from abc import ABC

import torch
from mmf.common.registry import registry


logger = logging.getLogger(__name__)


class TrainerDeviceMixin(ABC):
    def configure_seed(self) -> None:
        seed = self.config.training.seed
        if seed is None:
            return

        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    # TODO: Review self.device assignment and then override
    def configure_device(self) -> None:
        if self.config.training.get("device", "cuda") == "xla":
            import torch_xla.core.xla_model as xm
            self.device = xm.xla_device()
            self.distributed = True
            self.local_rank = xm.get_local_ordinal()
            self.xla = True
        else:
            self.xla = False
            self.local_rank = self.config.device_id
            self.device = self.local_rank
            self.distributed = False

        # Will be updated later based on distributed setup
        registry.register("global_device", self.device)

        if self.config.distributed.init_method is not None:
            self.distributed = True
            self.device = torch.device("cuda", self.local_rank)
        elif torch.cuda.is_available() and not self.xla:
            self.device = torch.device("cuda")
        elif not self.xla:
            self.device = torch.device("cpu")

        registry.register("current_device", self.device)
        registry.register("global_device", self.config.distributed.rank)

    def parallelize_model(self) -> None:
        registry.register("data_parallel", False)
        registry.register("distributed", False)
        if (
            "cuda" in str(self.device)
            and torch.cuda.device_count() > 1
            and not self.distributed
        ):
            registry.register("data_parallel", True)
            self.model = torch.nn.DataParallel(self.model)

        if "cuda" in str(self.device) and self.distributed:
            registry.register("distributed", True)
            self.model = torch.nn.parallel.DistributedDataParallel(
                self.model,
                device_ids=[self.local_rank],
                output_device=self.local_rank,
                check_reduction=True,
                find_unused_parameters=self.config.training.find_unused_parameters,
            )
