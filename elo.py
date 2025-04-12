import numpy as np

def calculate_elo(rating1: int, rating2: int, score1: int, score2: int, k_factor: int = 32) -> tuple[int, int]:
    """Calculate new ELO ratings for both players."""
    # Convert scores to expected format (1 for win, 0.5 for draw, 0 for loss)
    total_score = score1 + score2
    multiplier = 4/np.pi * np.arctan(total_score)
    
    actual_score1 = score1 / total_score
    actual_score2 = score2 / total_score
    
    # Calculate expected scores
    expected_score1 = 1 / (1 + 10 ** ((rating2 - rating1) / 400))
    expected_score2 = 1 / (1 + 10 ** ((rating1 - rating2) / 400))
    
    # Calculate new ratings
    new_rating1 = round(rating1 + k_factor * (actual_score1 - expected_score1) * multiplier)
    new_rating2 = round(rating2 + k_factor * (actual_score2 - expected_score2) * multiplier)
    
    return new_rating1, new_rating2 