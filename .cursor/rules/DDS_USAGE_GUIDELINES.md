# DDS Library Usage Guidelines

## Important: DDS Should NEVER Be Used for Bidding

### Key Principle
The DDS (Double Dummy Solver) library is **strictly for card play analysis only** and should **never be used during the bidding phase**.

### Correct Usage of DDS
- **Card Playing Phase Only**: Use DDS in `execute_robot_card_play()` function
- **Trick Analysis**: For optimal card play decisions during the play phase
- **Declarer vs Defender**: Different strategies based on role
- **Multiple Solutions**: Analyze multiple play options for best choice

### What DDS is NOT Used For
- ❌ **Bidding Decisions**: Never use DDS for opening bids, responses, or rebids
- ❌ **Hand Evaluation**: DDS doesn't evaluate hand strength for bidding
- ❌ **Convention Selection**: DDS doesn't choose bidding conventions
- ❌ **Auction Analysis**: DDS doesn't analyze bidding sequences

### Bidding System Architecture
The robot bidding system uses a **rule-based approach**:

1. **Primary**: SAYC (Standard American Yellow Card) bidding system
   - Hand evaluation (HCP, distribution points)
   - Bidding conventions (Jacoby transfers, Stayman, etc.)
   - Sequence-based decision making

2. **Fallback 1**: Advanced Fantoni-Nunes bidding engine
   - Algorithm-based bidding rules
   - Context-aware bidding decisions

3. **Fallback 2**: Basic bidding system
   - Simple HCP-based bidding
   - Emergency fallback

### Why DDS is Inappropriate for Bidding
- **Bidding is Convention-Based**: Bridge bidding relies on established conventions and agreements
- **DDS is Play-Oriented**: DDS analyzes card play, not bidding strategy
- **Performance**: DDS is computationally expensive and unnecessary for bidding
- **Accuracy**: Rule-based bidding is more accurate than DDS for auction decisions

### Implementation Notes
- DDS imports are only in `core/robot/robot_utils.py`
- Bidding systems (`sayc_bidding.py`, `advanced_bidding_engine.py`) have no DDS dependencies
- Clear separation between bidding and playing phases
- DDS wrapper (`working_dds_wrapper.py`) is only used for card play analysis

### Memory Reference
This guideline should be referenced whenever considering DDS usage in the BridgeLambdas project to ensure proper separation of concerns between bidding and playing phases.
