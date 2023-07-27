import glob
import torch
from datasets import load_dataset, load_from_disk
import os
import hnswlib
from torch.utils.data import DataLoader
from transformers import DefaultDataCollator
from .preprocess import tokenize_inputs


def load_data(config, tokenizer):
    dataset_path = config["dataset_path"]

    if os.path.exists(dataset_path):
        dataset = load_from_disk(dataset_path)
        # if os.path.isdir(dataset_path):
        #     files = glob.glob(os.path.join(dataset_path, "*_clean.jsonl"))
        # else:
        #     files = [dataset_path]

        # print(f"Reading files {files}")

        # dataset = load_dataset("json", data_files=files, split="train")

    else:
        dataset = load_dataset(dataset_path, split="train")

    dataset = dataset.train_test_split(test_size=.05, seed=config["seed"])

    dataset = dataset.map(lambda x: {"prompt": [text + " " + question for text, question in zip(x["text"], x["question"])]}, batched=True)

    train_dataset, val_dataset = dataset["train"], dataset["test"]

    if config["streaming"] is False:
        kwargs = {"num_proc": config["num_proc"]}
    else:
        kwargs = {}

    cols_to_keep = ["input_ids", "labels", "attention_mask"]

    # tokenize inputs and return labels and attention mask
    train_dataset = train_dataset.map(
        lambda ele: tokenize_inputs(config, tokenizer, ele, "prompt", "answer"),
        batched=True,
        # remove_columns=["source", "prompt"],
        **kwargs
    )

    cols_to_remove = [col for col in train_dataset.column_names if col not in cols_to_keep]
    train_dataset = train_dataset.remove_columns(cols_to_remove)

    val_dataset = val_dataset.map(
        lambda ele: tokenize_inputs(config, tokenizer, ele, "prompt", "answer"),
        batched=True,
        # remove_columns=["source", "prompt"],
        **kwargs
    )
    cols_to_remove = [col for col in val_dataset.column_names if col not in cols_to_keep]
    val_dataset = val_dataset.remove_columns(cols_to_remove)

    train_dataset = train_dataset.with_format("torch")
    val_dataset = val_dataset.with_format("torch")

    # create dataloader with default data collator since we already have labels

    train_dataloader = DataLoader(
        train_dataset,
        collate_fn=DefaultDataCollator(),
        batch_size=config["batch_size"],
        shuffle=True,
    )

    val_dataloader = DataLoader(
        val_dataset,
        collate_fn=DefaultDataCollator(),
        batch_size=config["batch_size"],
        shuffle=True,
    )

    return train_dataloader, val_dataloader


    
def load_data_for_inference(config, tokenizer):
    dataset_path = config["dataset_path"]

    if os.path.exists(dataset_path):
        # check if path is a directory
        if os.path.isdir(dataset_path):
            files = glob.glob(os.path.join(dataset_path, "*_clean.jsonl"))
        else:
            files = [dataset_path]

        print(f"Reading files {files}")

        dataset = load_dataset("json", data_files=files, split="train")

    else:
        dataset = load_dataset(dataset_path, split="train")

    dataset = dataset.train_test_split(test_size=.05, seed=config["seed"])

    train_dataset, val_dataset = dataset["train"], dataset["test"]

    train_dataset = train_dataset.add_column("index", list(range(len(train_dataset))))
    # select first N batches that are divisible by batch_size
    # gather is a bit annoying (or the way I'm using it) to get uneven batches as it duplicates data
    train_dataset = train_dataset.select(range((len(train_dataset) // config["batch_size"]) * config["batch_size"]))
    val_dataset = val_dataset.add_column("index", list(range(len(val_dataset))))
    val_dataset = val_dataset.select(range((len(val_dataset) // config["batch_size"]) * config["batch_size"]))

    if config["streaming"] is False:
        kwargs = {"num_proc": config["num_proc"]}
    else:
        kwargs = {}

    # tokenize inputs and return labels and attention mask
    train_dataset = train_dataset.map(
        lambda ele: tokenize_inputs(config, tokenizer, ele, "prompt", "response"),
        batched=True,
        **kwargs
    )
    val_dataset = val_dataset.map(
        lambda ele: tokenize_inputs(config, tokenizer, ele, "prompt", "response"), 
        batched=True,
        **kwargs
    )
    train_dataset = train_dataset.with_format("torch")
    val_dataset = val_dataset.with_format("torch")

    return train_dataset, val_dataset