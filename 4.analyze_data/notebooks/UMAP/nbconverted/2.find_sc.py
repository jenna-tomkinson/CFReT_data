#!/usr/bin/env python
# coding: utf-8

# # Find single cell images based on UMAP coordinates

# ## Import libraries

# In[1]:


import pathlib
import pandas as pd
from PIL import Image
import cv2
import numpy as np
import tifffile as tf
import yaml
from pprint import pprint


# ## Set variables and paths

# In[2]:


# Load in UMAP + metadata for each single cell as data frame
UMAP_plate3_df = pd.read_csv(
    pathlib.Path("./results/UMAP_localhost230405150001_sc_feature_selected.tsv.gz"), sep="\t"
)
print(UMAP_plate3_df.shape)

# Images directory for plate 3
images_dir = pathlib.Path(
    "../../../1.preprocessing_data/Corrected_Images/localhost230405150001/"
).resolve(strict=True)

# Directory with settings for each group on UMAP
settings_dir = pathlib.Path("./image_settings/")

# Output dir for composite and cropped images
output_img_dir = pathlib.Path("./images")
output_img_dir.mkdir(exist_ok=True)


# ## Read in `yaml` file with settings for each single cell type
# 
# There is a `yaml` file called *image_settings.yaml* that holds the dictionary for all of the different UMAP single cells that we want to crop.
# 
# There are 4 variables per single cell:
# - **Random state** -> number used to select the random row from the filtered UMAP data frame using the ranges set for the UMAP
# - **UMAP0** -> range of values on the x-axis corresponding to a cluster
# - **UMAP1** -> range of values on the y-axis corresponding to a cluster
# - **composite_save_path** -> path to save full RGB composite image
# - **crop_save_path** -> path to save cropped single cell RGB image
# 
# `UMAP0` and `UMAP1` variables are used to filter the UMAP data frame to only find single cells from specific clusters.

# In[3]:


# load in plate information
dictionary_path = pathlib.Path(f"{settings_dir}/right_cluster.yaml")
with open(dictionary_path) as file:
    cell_info_dictionary = yaml.load(file, Loader=yaml.FullLoader)

# Set output dirs based on the dictionary loaded in
comp_dir = pathlib.Path(f"./images/composite_imgs/{dictionary_path.stem}")
comp_dir.mkdir(exist_ok=True)
crop_dir = pathlib.Path(f"./images/cropped_imgs/{dictionary_path.stem}")
crop_dir.mkdir(exist_ok=True)

# Display the first two nested dictionaries to make sure the dictionary looks correct
pprint(list(cell_info_dictionary.items())[:2], indent=4)


# ## Find single cells from each cell type and treatment from UMAP (plate 3)

# In[4]:


for crop_cell, info in cell_info_dictionary.items():
    # Define your filter conditions
    condition = (
        (UMAP_plate3_df['Metadata_cell_type'] == crop_cell.split('-')[0]) &
        (UMAP_plate3_df['Metadata_treatment'] == crop_cell.split('-')[1]) &
        (UMAP_plate3_df['UMAP0'].between(info["UMAP0"][0], info["UMAP0"][1]) &
        (UMAP_plate3_df['UMAP1'].between(info["UMAP1"][0], info["UMAP1"][1]))
    ))

    # Apply the filter and select only the specific columns
    filtered_df = UMAP_plate3_df[condition][[
        'Metadata_cell_type',
        'Metadata_treatment',
        'Metadata_Plate',
        'Metadata_Well',
        'Metadata_Site',
        'Metadata_Cells_Location_Center_X',
        'Metadata_Cells_Location_Center_Y',
        'UMAP0',
        'UMAP1'
    ]]

    # Randomly select a row using the random state parameter
    random_row = filtered_df.sample(n=1, random_state=info["Random state"])  

    # Create a filename based on Metadata_Plate, Metadata_Well, Metadata_Site
    plate = random_row['Metadata_Plate'].values[0]
    well = random_row['Metadata_Well'].values[0]
    site = random_row['Metadata_Site'].values[0]

    # Initialize a list to store file paths
    file_paths = []

    # Create 5 different file paths with "d0" through "d4" suffixes
    for i in range(5):
        filename = f"{images_dir}/{plate}_{well}{site}d{i}_illumcorrect.tiff"
        file_paths.append(filename)

    print("Randomly selected row:")
    print(random_row)
    print("Generated filenames:")
    for path in file_paths:
        print(path)

    # Initialize empty lists to store the images for each channel
    blue_channel = []
    green_channel = []
    red_channel = []

    # Iterate through channels from the random well/site and assign the correct file names with the color channel
    for file_path in file_paths:
        filename = pathlib.Path(file_path).name
        if 'd0' in filename:
            blue_channel_image = cv2.imread(str(file_path), cv2.IMREAD_UNCHANGED)
            blue_channel.append(blue_channel_image)
        elif 'd1' in filename:
            green_channel_image = cv2.imread(str(file_path), cv2.IMREAD_UNCHANGED)
            green_channel.append(green_channel_image)
        elif 'd4' in filename:
            red_channel_image = cv2.imread(str(file_path), cv2.IMREAD_UNCHANGED)
            red_channel.append(red_channel_image)

    # Stack the images for each channel along the channel axis
    blue_channel_stack = np.stack(blue_channel, axis=-1)
    green_channel_stack = np.stack(green_channel, axis=-1)
    red_channel_stack = np.stack(red_channel, axis=-1)

    # Scale the pixel values to fit within the 16-bit range (0-65535)
    blue_channel_stack = (blue_channel_stack / np.max(blue_channel_stack) * 65535).astype(np.uint16)
    green_channel_stack = (green_channel_stack / np.max(green_channel_stack) * 65535).astype(np.uint16)
    red_channel_stack = (red_channel_stack / np.max(red_channel_stack) * 65535).astype(np.uint16)

    # Create the RGB numpy array by merging the channels
    composite_image = cv2.merge((red_channel_stack, green_channel_stack, blue_channel_stack)).astype(np.uint16)

    # Path for saving comp images
    comp_path = pathlib.Path(f"{comp_dir}/{info['composite_save_path']}")

    # Save the composite 16-bit RGB tiff image
    tf.imwrite(comp_path, composite_image)

    # Load the composite image from the save path as an Image object instead of numpy array
    with Image.open(comp_path) as composite_image:

        # Assuming you have a DataFrame called "filtered_df" with center coordinates
        center_x = random_row["Metadata_Cells_Location_Center_X"]
        center_y = random_row["Metadata_Cells_Location_Center_Y"]

        # Define the size of the cropping box (250x250 pixels)
        box_size = 250

        # Paths for saving cropped images
        crop_path = pathlib.Path(f"{crop_dir}/{info['crop_save_path']}")

        # Iterate through the center coordinates and crop each cell
        for x, y in zip(center_x, center_y):
            left = x - box_size // 2
            top = y - box_size // 2
            right = x + box_size // 2
            bottom = y + box_size // 2

            # Crop the cell
            cell_image = composite_image.crop((left, top, right, bottom))

            # Save the cropped cell image with a unique name, you can use the cell's ID or index
            cell_image.save(crop_path)

